# main.py
# LetItRain v1.2.0 — Multi-zone scheduler
#
# Architecture:
#   - Multi-zone relay control (up to 5 zones, configurable GPIO pins)
#   - Multi-slot scheduler: multiple start times per day, per zone
#   - HTTP JSON API for local iOS control
#   - Firebase writer: status heartbeat + meta (IP, zone count)
#   - Firebase reader: schedule + zone config sync every 60s
#   - Firebase override reader: skip-today support

import utime
import gc
import _thread
from machine import I2C, Pin, reset, WDT

import secrets
from secrets import (
    WIFI_SSID, WIFI_PASSWORD,
    FIREBASE_API_KEY, FIREBASE_EMAIL, FIREBASE_PASSWORD,
    FIREBASE_DB_URL, FIREBASE_DEVICE_ID, FIREBASE_STORAGE_BUCKET,
)

from netcfg.wifi import connect_wifi

from hardware.relay       import ZoneRelayController
from hardware.ds3231      import DS3231
from hardware.status_led  import StatusLED
from hardware.lcd1602     import LCD1602
from hardware.lcd_status  import LCDStatus
from storage.config_store import load_config, save_config
from core.state           import ControllerState
from core.scheduler       import get_pending_slot, clear_old_slot_runs, get_next_slot
from core.unix_time       import unix_time, to_unix

from firebase.client      import FirebaseClient
from firebase.status_writer  import StatusWriter
from firebase.override_reader import OverrideReader
from firebase.schedule_sync  import ScheduleSync
from web.server           import run_server
from update.updater       import check_for_update, get_status as get_ota_status, get_local_version
from core                 import mem_diag

# ---------------------------------------------------------------------------
# Boot — load config, init hardware
# relay.all_off() MUST be the very first hardware operation.
# Status LEDs: green = GPIO16, red = GPIO17 (see README wiring notes).
# ---------------------------------------------------------------------------

try:
    config = load_config()
    state  = ControllerState()

    relay = ZoneRelayController(
        zones_config=config.get("zones", []),
        active_high=config.get("relay_active_high", True),
    )
    relay.all_off()   # ← SAFETY: de-energise all relays on every boot

    status_led = StatusLED(green_pin=16, red_pin=17)
    status_led.set_mode("booting")

    # LCD is non-fatal like the RTC below -- an unwired/broken backpack
    # shouldn't take the whole controller down, it just means no display.
    try:
        lcd        = LCD1602(dat_pin=18, clk_pin=19, lat_pin=20)
        lcd_status = LCDStatus(lcd)
        lcd_status.show_message("Booting")
    except Exception as ex:
        print("LCD init failed (not wired?):", ex)
        lcd_status = None

    i2c = I2C(0, sda=Pin(0), scl=Pin(1), freq=100000)
    try:
        rtc = DS3231(i2c)
        rtc.datetime_tuple()   # probe — DS3231() alone never touches the bus
    except Exception as ex:
        print("RTC init failed (not wired?):", ex)
        rtc = None
except Exception as ex:
    # relay.all_off() (above) already ran before any of the later steps that
    # could fail, so there's nothing left needing a fallback shutoff here.
    print("FATAL boot error:", ex)
    _failed_led = StatusLED(green_pin=16, red_pin=17)
    _failed_led.set_mode("boot_failed")
    try:
        LCDStatus(LCD1602(dat_pin=18, clk_pin=19, lat_pin=20)).show_message(
            "ERR: {}".format(ex))
    except Exception:
        pass  # LCD may not be wired -- the LED is the guaranteed indicator
    while True:
        _failed_led.tick()
        utime.sleep_ms(50)

# Tracks which schedule slots have already fired today: {"monday_0": epoch, ...}
last_run_slots = {}

# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def get_now_epoch():
    """True UTC epoch — used for Firebase timestamps, run-duration math, and
    anything the app compares against Date().timeIntervalSince1970. The
    DS3231 (when present) is kept synced to UTC via NTP at boot, so both
    branches below return the same true-UTC convention."""
    if rtc:
        return to_unix(rtc.epoch())
    return unix_time()


def get_local_wall_clock_epoch():
    """Epoch-shaped value representing LOCAL wall-clock time — for schedule
    matching and "today's date" only. MicroPython has no timezone database,
    so this is a fixed manual offset (-5 = EST TODO: Make this config driven in app, no
    DST). Never send this to Firebase/the app — it is not a real timestamp."""
    return get_now_epoch() + (-5 * 3600)


def get_now_date_string():
    """Return today's LOCAL date as 'YYYY-MM-DD' for skip-date comparisons."""
    t = utime.localtime(get_local_wall_clock_epoch())
    return "{:04d}-{:02d}-{:02d}".format(t[0], t[1], t[2])


def _format_ip_version(ip, version):
    """Fit "<ip> v<version>" into the LCD's 16-char bottom row. If the
    full IP doesn't leave room for the version, shorten it to its last
    two octets rather than truncating the version -- almost every home
    LAN is 192.168.x.x/10.x.x.x, so the tail is still enough to recognise
    the device, whereas a truncated version silently hides the patch
    number."""
    version_text = "v" + version
    if len(ip) + 1 + len(version_text) <= 16:
        return ip, version_text
    parts = ip.split(".")
    if len(parts) == 4:
        short_ip = ".".join(parts[-2:])
        if len(short_ip) + 1 + len(version_text) <= 16:
            return short_ip, version_text
    return ip, version_text  # LCDStatus's own row-truncation is the fallback


# ---------------------------------------------------------------------------
# Run control
# ---------------------------------------------------------------------------

def start_run(zone_id, duration_seconds, mode):
    """Start a zone. If another zone is running, stop it first."""
    if state.is_running():
        _stop_relay_for_current_zone()
    now_epoch = get_now_epoch()
    relay.on(zone_id)
    state.start_run(now_epoch, duration_seconds, mode, zone_id)
    print("Run started: zone={} mode={} duration={}s".format(zone_id, mode, duration_seconds))


def _stop_relay_for_current_zone():
    if state.current_zone_id:
        relay.off(state.current_zone_id)


def stop_run(status_str="completed"):
    if not state.is_running():
        relay.all_off()
        return
    start_epoch = state.current_run_start_epoch
    mode        = state.current_run_mode
    zone_id     = state.current_zone_id
    end_epoch   = get_now_epoch()

    _stop_relay_for_current_zone()
    state.stop_run()

    config["last_run"] = {
        "start_epoch": start_epoch,
        "end_epoch":   end_epoch,
        "mode":        mode,
        "zone_id":     zone_id,
        "status":      status_str,
    }
    save_config(config)
    print("Run stopped: zone={} status={}".format(zone_id, status_str))

    if status_writer is not None:
        try:
            status_writer.push_last_run(start_epoch, end_epoch, mode, zone_id, status_str)
        except Exception as ex:
            print("Firebase push_last_run failed (non-fatal):", ex)


def on_manual_start(zone_id=1, duration_minutes=None):
    mins = duration_minutes or config.get("manual_default_duration_minutes", 10)
    start_run(int(zone_id), int(mins) * 60, "manual")


def on_manual_stop():
    stop_run("manual_stop")


# ---------------------------------------------------------------------------
# Local override state (shared with HTTP thread)
# ---------------------------------------------------------------------------

local_override = {"skip_today": False, "skip_reason": None}

# ---------------------------------------------------------------------------
# HTTP server thread
# ---------------------------------------------------------------------------

def start_web_server():
    try:
        run_server(
            config=config,
            state=state,
            rtc=rtc,
            on_manual_start=on_manual_start,
            on_manual_stop=on_manual_stop,
            local_override=local_override,
            save_config_fn=save_config,
            now_fn=get_now_epoch,
            firmware_version=firmware_version,
        )
    except Exception as ex:
        print("HTTP server thread crashed:", ex)


# ---------------------------------------------------------------------------
# Module-level reference so stop_run() can call status_writer
# ---------------------------------------------------------------------------

status_writer    = None
override_reader  = None
schedule_sync    = None
firmware_version = None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global status_writer, override_reader, schedule_sync, firmware_version

    # Single source of truth for the running version: whatever the OTA
    # updater last wrote to version.json. This keeps the displayed version
    # in sync automatically after every successful update, with no separate
    # constant to remember to bump.
    firmware_version = get_local_version()

    print("LetItRain v{} booting...".format(firmware_version))
    print("Zones configured:", relay.zone_ids())

    # --- Wi-Fi ---
    wlan     = None
    local_ip = "0.0.0.0"
    try:
        wlan = connect_wifi(WIFI_SSID, WIFI_PASSWORD, on_wait=status_led.tick)
        local_ip = wlan.ifconfig()[0]
        if local_ip == "0.0.0.0":
            # wlan.isconnected() can flip true a beat before the DHCP lease
            # is actually reflected in ifconfig() — give it a moment rather
            # than pushing the placeholder IP the app treats as invalid.
            for _ in range(10):
                utime.sleep_ms(200)
                local_ip = wlan.ifconfig()[0]
                if local_ip != "0.0.0.0":
                    break
    except Exception as ex:
        print("Wi-Fi failed (non-fatal, running offline):", ex)
        # connect_wifi() can time out right as the connection is actually
        # completing (status flips CONNECTING -> NOIP -> UP in the last
        # couple of attempts, then DHCP finishes moments after we gave up).
        # One more check here, on a fresh handle to the same physical
        # interface, catches that instead of silently keeping 0.0.0.0.
        try:
            import network
            wlan = network.WLAN(network.STA_IF)
            if wlan.isconnected():
                local_ip = wlan.ifconfig()[0]
                print("Wi-Fi: connected shortly after timeout, IP:", local_ip)
        except Exception:
            pass

    # --- Hardware watchdog ---
    # Armed here, right after Wi-Fi settles, not any earlier: Wi-Fi retries
    # alone can legitimately take up to ~20s, which exceeds the RP2040's
    # ~8.3s max WDT timeout, so arming any earlier would false-trigger
    # during a normal boot. Everything from here on (NTP, Firebase auth,
    # boot-time schedule sync, OTA check) is fed between steps below for
    # the same reason the main loop feeds between sections rather than
    # once per pass -- a single stuck call (a wedged Wi-Fi driver, a socket
    # that never returns even past its own timeout, whatever the next
    # lockup turns out to be) now actually triggers a hard reset instead of
    # hanging forever unrecovered, which a boot-time hang previously would
    # have done since nothing was armed yet to catch it.
    wdt = WDT(timeout=8000)

    # --- NTP time sync ---
    # Without this, utime.time() stays at its arbitrary boot-time default
    # instead of the real date, and every timestamp sent to Firebase/the
    # app (heartbeats, run times) will be meaningless.
    try:
        import ntptime
        ntptime.settime()
        print("NTP: time synced")

        # Keep the DS3231 in true UTC too, so it agrees with unix_time()
        # whenever Wi-Fi is down and get_now_epoch() falls back to it. This
        # replaces manually running set_rtc_once.py -- and fixes it if that
        # script was ever run with the wrong value.
        if rtc is not None:
            t = utime.localtime(unix_time())  # UTC fields, no offset applied
            rtc.set_datetime(t[0], t[1], t[2], t[3], t[4], t[5], t[6] + 1)
            print("RTC: synced from NTP to", rtc.iso_string())
    except Exception as ex:
        print("NTP: sync failed (non-fatal):", ex)
    wdt.feed()

    # --- Firebase ---
    fb = FirebaseClient(
        api_key=FIREBASE_API_KEY, email=FIREBASE_EMAIL,
        password=FIREBASE_PASSWORD, db_url=FIREBASE_DB_URL,
        device_id=FIREBASE_DEVICE_ID,
    )
    firebase_ok = False
    try:
        firebase_ok = fb.authenticate()
    except Exception as ex:
        print("Firebase auth failed (non-fatal):", ex)
    wdt.feed()

    # Optional sanity check against secrets.py's FIREBASE_EXPECTED_UID (only
    # present if the deployer filled it in after a first successful boot).
    # Catches "flashed the wrong friend's secrets.py onto this board" right
    # here, instead of via a confusing permission failure several steps
    # later once device_owner_uid rejects a write from the wrong account.
    expected_uid = getattr(secrets, "FIREBASE_EXPECTED_UID", None)
    if firebase_ok and expected_uid and fb.uid != expected_uid:
        print("Firebase: WARNING authenticated UID {} != FIREBASE_EXPECTED_UID "
              "{} in secrets.py -- wrong device credentials for this "
              "Pico?".format(fb.uid, expected_uid))

    # Claim (or verify) ownership of this device_id's meta/status nodes.
    # The security rules let whichever account first writes here become the
    # permanent owner -- this is what makes a fresh Firebase project work
    # with zero manual "paste your UID into the rules" step per deployment.
    # A rejected claim here means this device_id is already owned by a
    # different account (e.g. two friends both left FIREBASE_DEVICE_ID at
    # its default value) -- surfaced immediately and specifically, instead
    # of as a generic meta-patch 401 several boot steps later.
    if firebase_ok:
        try:
            if not fb.put("device_owner_uid", fb.uid):
                print("Firebase: device_owner_uid claim failed -- this "
                      "device_id may already be owned by a different "
                      "account. Pick a unique FIREBASE_DEVICE_ID.")
                if lcd_status:
                    lcd_status.show_message("ID already used")
        except Exception as ex:
            print("Firebase: device_owner_uid claim exception (non-fatal):", ex)
        wdt.feed()

    status_writer   = StatusWriter(fb, state, config, firmware_version,
                                   config.get("device_name", "LetItRain Controller"))
    override_reader = OverrideReader(fb)
    schedule_sync   = ScheduleSync(fb, config, save_config)

    update_pending = False

    if firebase_ok:
        try:
            schedule_sync.push_initial()   # seed Firebase if empty
            schedule_sync.sync()           # pull latest schedule/zones
            status_led.set_mode("running")
        except Exception as ex:
            print("Firebase boot sync failed (non-fatal):", ex)
            status_led.set_mode("no_internet")
        wdt.feed()

        # Pushed in its own try block: the app relies on meta/local_ip to know
        # which IP to probe for local mode, so a schedule-sync failure above
        # must never prevent this from being written.
        try:
            status_writer.push_ip(local_ip)
        except Exception as ex:
            print("Firebase push_ip failed (non-fatal):", ex)
        wdt.feed()

        try:
            if lcd_status:
                lcd_status.show_message("Updating")
            update_pending = check_for_update(FIREBASE_STORAGE_BUCKET, fb.id_token)
        except Exception as ex:
            print("OTA update check failed (non-fatal):", ex)
        wdt.feed()
    else:
        status_led.set_mode("no_internet")

    # --- HTTP server thread ---
    try:
        _thread.start_new_thread(start_web_server, ())
    except Exception as ex:
        print("HTTP thread start failed:", ex)
    wdt.feed()

    # --- Timing ---
    last_status_push  = 0
    last_schedule_sync = 0
    last_ip_push       = utime.time()
    last_update_check  = utime.time()
    last_ota_poll      = utime.time()
    last_ota_status_pushed = None
    # Relaxed from the original 15/60/30s: the app tolerates 30-45s of
    # staleness on everything, and every one of these is a Firebase/TLS
    # round-trip competing for this board's limited RAM -- halving the call
    # rate directly eases that pressure, not just a latency trade-off.
    STATUS_INTERVAL   = 30
    SYNC_INTERVAL     = 90
    IP_PUSH_INTERVAL  = 300  # re-check/re-push local_ip every 5 min
    OTA_POLL_INTERVAL = 45   # manual "check now" trigger + status push

    # wdt was already armed right after Wi-Fi settled, above -- from here
    # on it's fed after each section below (heartbeat, OTA poll, IP check,
    # schedule sync, ...) and every 100ms in the LED-tick loop, not wrapped
    # around any single blocking call. Each Firebase call has its own ~8s
    # internal timeout, and several can legitimately fire in the same pass,
    # so feeding only once per full iteration could stack those timeouts
    # past 8s during an ordinary internet outage and false-trigger. Feeding
    # between sections means only a call that never returns at all (I2C
    # contention, a wedged Wi-Fi driver, memory exhaustion, whatever the
    # next lockup turns out to be) goes unfed long enough to reset.
    # relay.all_off() is unconditionally the first thing that runs on every
    # boot, so this guarantees water stops within seconds of any such hang,
    # even one we never manage to root-cause.

    # Baseline heap reading -- the arena size is fixed at boot on
    # MicroPython, so this total is the real RAM ceiling to compare
    # min_free_mem_bytes (in /status and the Firebase heartbeat) against
    # when deciding whether headroom is actually tight enough to justify
    # a Pico 2 W.
    gc.collect()
    mem_diag.sample()
    print("Heap: {} bytes total, {} free at boot".format(
        mem_diag.heap_total(), gc.mem_free()))

    print("Main loop started.")

    try:
        while True:
            try:
                now_epoch       = get_now_epoch()             # true UTC — run/Firebase math
                local_epoch     = get_local_wall_clock_epoch()  # local wall clock — scheduling only
                now_date_string = get_now_date_string()
                wdt.feed()  # covers I2C/RTC access above, if that's ever the hang

                # --- LCD status refresh ---
                # Cheap to call every pass (~5s): no I/O of its own, and
                # LCDStatus only actually touches the display when a
                # field's text changed since the last draw.
                if lcd_status:
                    zone_text = ("Zone {}".format(state.current_zone_id)
                                 if state.is_running() else "Idle")
                    next_slot = get_next_slot(config.get("schedule", {}),
                                              last_run_slots, local_epoch)
                    if next_slot:
                        next_day, next_hour, next_minute, _next_zone = next_slot
                        # str.capitalize() doesn't exist in MicroPython's
                        # minimal string implementation -- do it by hand.
                        day_abbr = next_day[:3]
                        day_abbr = day_abbr[0].upper() + day_abbr[1:]
                        next_text = "{} {:02d}:{:02d}".format(
                            day_abbr, next_hour, next_minute)
                    else:
                        next_text = "No sched"
                    ip_text, version_text = _format_ip_version(local_ip, firmware_version)
                    lcd_status.show_status(zone_text, next_text, ip_text, version_text)

                # --- Stop check ---
                if state.should_stop_now(now_epoch):
                    stop_run("completed")

                # --- Scheduler ---
                if not state.is_running():
                    clear_old_slot_runs(last_run_slots, local_epoch)

                    slot, slot_key = get_pending_slot(
                        config.get("schedule", {}),
                        state,
                        last_run_slots,
                        local_epoch,
                    )

                    if slot and slot_key:
                        # Check skip override
                        skip_active = local_override["skip_today"]
                        skip_reason = local_override["skip_reason"]
                        if not skip_active:
                            try:
                                skip_active, skip_reason = override_reader.get_active_skip(
                                    now_date_string)
                            except Exception as ex:
                                print("Override read error (fail open):", ex)
                                skip_active = False

                        if skip_active:
                            print("Scheduled slot skipped:", slot_key, "reason:", skip_reason)
                            last_run_slots[slot_key] = local_epoch  # mark as handled
                            # FUTURE v1.2: rain_inches threshold check here
                        else:
                            zone_id          = slot.get("zone", 1)
                            duration_seconds = slot.get("duration_minutes", 10) * 60
                            start_run(zone_id, duration_seconds, "scheduled")
                            last_run_slots[slot_key] = local_epoch

                # --- Firebase heartbeat ---
                # Kept to a single request: this loop is single-threaded, so
                # anything else stacked here directly delays how often this
                # specific call can land, and it's the one the app's
                # "device online" freshness check depends on.
                if utime.time() - last_status_push >= STATUS_INTERVAL:
                    try:
                        status_writer.push_status(
                            active_skip=local_override["skip_today"],
                            active_skip_reason=local_override["skip_reason"],
                        )
                        status_led.set_mode("running")
                    except Exception as ex:
                        print("Firebase heartbeat failed (non-fatal):", ex)
                        status_led.set_mode("no_internet")
                    last_status_push = utime.time()
                    wdt.feed()

                # --- Manual OTA trigger + status push ---
                # Own interval, separate from the heartbeat above, so a
                # pending "check now" from the app doesn't add extra
                # round-trips to the time-sensitive online/offline signal.
                if utime.time() - last_ota_poll >= OTA_POLL_INTERVAL:
                    if not update_pending and fb.id_token:
                        try:
                            update_info = fb.get("update") or {}
                            if update_info.get("requested"):
                                fb.patch("update", {"requested": False})  # clear so it fires once
                                if lcd_status:
                                    lcd_status.show_message("Updating")
                                update_pending = check_for_update(FIREBASE_STORAGE_BUCKET, fb.id_token)
                        except Exception as ex:
                            print("OTA trigger check failed (non-fatal):", ex)

                    # Skip the push entirely when nothing changed -- this is
                    # "idle" nearly every tick in normal operation, and every
                    # skipped push is one fewer TLS handshake competing for
                    # this board's very limited RAM.
                    current_ota_status = get_ota_status()
                    if current_ota_status != last_ota_status_pushed:
                        try:
                            if fb.patch("update", current_ota_status):
                                last_ota_status_pushed = current_ota_status
                        except Exception:
                            pass

                    last_ota_poll = utime.time()
                    wdt.feed()

                # --- Local IP re-check ---
                # Catches DHCP lease renewals / router reboots that hand the
                # Pico a new address after boot, so meta/local_ip in Firebase
                # never goes stale for longer than IP_PUSH_INTERVAL.
                if utime.time() - last_ip_push >= IP_PUSH_INTERVAL:
                    if wlan is not None and wlan.isconnected():
                        try:
                            current_ip = wlan.ifconfig()[0]
                            # Never adopt/push "0.0.0.0" — ifconfig() can read
                            # that transiently during a DHCP lease renewal,
                            # and pushing it would overwrite a known-good IP
                            # in Firebase with a value the app treats as
                            # invalid until the next 5-minute cycle.
                            if current_ip != "0.0.0.0" and current_ip != local_ip:
                                local_ip = current_ip
                            if local_ip != "0.0.0.0":
                                status_writer.push_ip(local_ip)
                        except Exception as ex:
                            print("Firebase push_ip failed (non-fatal):", ex)
                    last_ip_push = utime.time()
                    wdt.feed()

                # --- Schedule sync ---
                if utime.time() - last_schedule_sync >= SYNC_INTERVAL:
                    try:
                        schedule_sync.sync()
                        # If zones changed, re-init relay controller would need reboot
                        # For now: log a note; zone hardware changes require reboot
                    except Exception as ex:
                        print("Schedule sync failed (non-fatal):", ex)
                    last_schedule_sync = utime.time()
                    wdt.feed()

                # An update was downloaded and is staged — apply it as soon as
                # no zone is actively running, so a reboot never cuts a run short.
                if update_pending and not state.is_running():
                    print("OTA: applying staged update, rebooting...")
                    relay.all_off()
                    reset()

            except Exception as ex:
                print("Main loop error:", ex)
                relay.all_off()
                if lcd_status:
                    try:
                        lcd_status.show_message("ERR: {}".format(ex))
                    except Exception:
                        pass

            # Tick the LED every 100ms during the 5s pause so its pattern
            # stays accurate instead of only updating once per loop pass.
            # Also feeds the watchdog -- see the WDT comment above for why
            # it's fed here specifically and nowhere else.
            for _ in range(50):
                status_led.tick()
                wdt.feed()
                utime.sleep_ms(100)

            # Defensive backstop for passes where nothing above touched a
            # socket (e.g. no interval elapsed yet) and so never triggered
            # one of the collect-right-after-close() calls elsewhere --
            # this 5s idle window is otherwise dead time, so the cost is
            # free.
            mem_diag.sample()
            gc.collect()

    finally:
        relay.all_off()
        status_led.set_mode("boot_failed")
        try:
            status_writer.push_offline()
        except Exception:
            pass


main()
