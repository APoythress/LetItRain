# main.py
# LetItRain v2.0.0-alpha — Raspberry Pi 3 A+ (CPython 3 / Linux)
#
# Architecture:
#   - asyncio, single process, single event loop -- every concern below is
#     an independent task, restoring real per-concern cadences instead of
#     the Pico build's one batched 15-min cloud-sync pass (that batching
#     only existed to work around the Pico W's CYW43 WiFi chip wedging
#     under frequent TLS traffic; a full Linux network stack has no
#     equivalent failure mode).
#   - Multi-zone relay control (gpiozero), multi-slot scheduler (unchanged
#     logic from the Pico build), local FastAPI JSON API for the iOS app.
#   - Firebase: status/meta pushed on their own cadence, schedule/zones
#     pushed on a slower cadence, overrides read only when a scheduled
#     slot is about to fire.
#   - WiFi and NTP are OS-managed (NetworkManager/wpa_supplicant,
#     systemd-timesyncd) -- this process no longer manages either itself.
#     The DS3231 seeds the system clock at boot if it looks unset, and is
#     periodically mirrored from the (OS-synced) system clock afterward.
#   - Process supervision/watchdog is systemd's (see deploy/letitrain.service)
#     -- this sends sd_notify(WATCHDOG=1) on its own heartbeat instead of
#     the Pico build's manual machine.WDT.feed() calls.
#   - OTA updates are git-tag-based (see firebase/update_checker.py) --
#     replaces update/updater.py, which was MicroPython/Pico-only and
#     never applicable here. No push notifications yet: the app surfaces
#     an "update available" badge from the same Firebase status this
#     writes, and the user drives it from there.

import asyncio
import json
import os
import socket
import subprocess
import sys
import time

import uvicorn

from device_secrets import (
    FIREBASE_API_KEY, FIREBASE_EMAIL, FIREBASE_PASSWORD,
    FIREBASE_DB_URL, FIREBASE_DEVICE_ID, FIREBASE_STORAGE_BUCKET,
)

from hardware.relay        import ZoneRelayController
from hardware.ds3231       import DS3231
from hardware.status_led   import StatusLED
from hardware.lcd1602      import LCD1602
from hardware.lcd_status   import LCDStatus
from storage.config_store  import load_config, save_config
from core.state            import ControllerState
from core.scheduler        import get_pending_slot, clear_old_slot_runs, get_next_slot
from core.unix_time        import unix_time, local_wall_clock_epoch

from firebase.client         import FirebaseClient
from firebase.status_writer  import StatusWriter
from firebase.override_reader import OverrideReader
from firebase.schedule_sync  import ScheduleSync
from firebase                import update_checker
from web.server             import create_app

FIRMWARE_VERSION = "2.0.0-alpha"
BOOT_LOG_FILE    = "boot_log.json"

# Independent sync cadences -- each concern gets its own real interval now
# instead of being folded into one batched pass. Tune freely; none of these
# share a failure mode with each other the way they did on the Pico.
LOCAL_TICK_INTERVAL  = 2      # seconds -- scheduler/stop-check/LCD refresh
STATUS_SYNC_INTERVAL = 60     # seconds -- Firebase status push
META_SYNC_INTERVAL   = 300    # seconds -- Firebase zones/schedule/IP push
RTC_MIRROR_INTERVAL  = 3600   # seconds -- mirror system clock into DS3231
WATCHDOG_INTERVAL    = 10     # seconds -- must be well under the systemd
                               # unit's WatchdogSec/2 (see deploy/letitrain.service)
UPDATE_POLL_INTERVAL  = 300    # seconds -- how often we check Firebase for an
                                # "Update Now" tap or a manual "Check Now" request
UPDATE_CHECK_INTERVAL = 21600  # seconds (6h) -- how often we check for a new
                                # version at all, absent a manual request


# ---------------------------------------------------------------------------
# systemd integration -- no external dependency, just the documented
# sd_notify wire protocol (a datagram to the Unix socket named in
# $NOTIFY_SOCKET). No-ops outside systemd (e.g. running main.py by hand).
# ---------------------------------------------------------------------------

def _sd_notify(message):
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return
    if addr[0] == "@":
        addr = "\0" + addr[1:]  # abstract namespace socket
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(addr)
            sock.sendall(message.encode())
    except Exception as ex:
        print("sd_notify failed (non-fatal):", ex)


async def watchdog_loop():
    """Heartbeat task: tells systemd's hardware watchdog this process is
    still alive. If this task itself ever stops running (event loop
    wedged, not just one call hanging), systemd's WatchdogSec deadline
    passes with no WATCHDOG=1 received and the unit gets hard-restarted --
    the same ultimate safety net the Pico's manual wdt.feed() calls were,
    now owned by the OS instead of hand-rolled."""
    _sd_notify("READY=1")
    while True:
        await asyncio.sleep(WATCHDOG_INTERVAL)
        _sd_notify("WATCHDOG=1")


# ---------------------------------------------------------------------------
# Networking helpers -- WiFi association itself is OS-managed (see module
# header); these are just cheap checks/lookups the app still needs.
# ---------------------------------------------------------------------------
#region
def local_ip():
    """Best-effort local IP via the outbound-UDP-socket trick (no packets
    actually sent -- connect() on a UDP socket just picks the interface/
    source address the kernel would route through). No netifaces
    dependency, same trick on any Linux box."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "0.0.0.0"


async def network_reachable(host="8.8.8.8", port=443, timeout=3):
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False
#endregion

# ---------------------------------------------------------------------------
# DS3231 <-> system clock
# ---------------------------------------------------------------------------
#region
def seed_system_clock_from_rtc(rtc):
    """Best-effort boot-time seed: if the system clock looks unset (before
    2020 -- a fresh Pi with no RTC battery backup and no network yet boots
    to the Unix epoch or its last shutdown time), trust the DS3231 (kept in
    UTC) until systemd-timesyncd corrects it once the network comes up.
    Requires permission to set the system clock -- normally fine, since
    this service runs as root (see deploy/letitrain.service)."""
    if rtc is None:
        return
    try:
        if time.time() < 1577836800:  # 2020-01-01T00:00:00Z
            rtc_epoch = rtc.epoch()
            subprocess.run(["date", "-u", "-s", "@{}".format(rtc_epoch)], check=True)
            print("Boot: system clock seeded from DS3231:", rtc.iso_string())
    except Exception as ex:
        print("Boot: RTC clock seed failed (non-fatal):", ex)


def mirror_system_clock_to_rtc(rtc):
    """Periodic: write the (OS-synced) system clock back into the DS3231,
    same direction as the Pico build's daily NTP resync, just without this
    process running its own NTP client -- systemd-timesyncd already keeps
    the system clock correct."""
    if rtc is None:
        return
    try:
        now = time.gmtime(unix_time())
        rtc.set_datetime(now.tm_year, now.tm_mon, now.tm_mday,
                          now.tm_hour, now.tm_min, now.tm_sec,
                          now.tm_wday + 1)
        print("RTC: mirrored system clock ->", rtc.iso_string())
    except Exception as ex:
        print("RTC mirror failed (non-fatal):", ex)
#endregion


def _write_boot_log(log):
    try:
        with open(BOOT_LOG_FILE, "w") as f:
            json.dump(log, f)
    except Exception as ex:
        print("Boot log write failed (non-fatal):", ex)


def _format_ip_version(ip, version):
    """Fit "<ip> v<version>" into the LCD's 16-char bottom row -- unchanged
    from the Pico build."""
    version_text = "v" + version
    if len(ip) + 1 + len(version_text) <= 16:
        return ip, version_text
    parts = ip.split(".")
    if len(parts) == 4:
        short_ip = ".".join(parts[-2:])
        if len(short_ip) + 1 + len(version_text) <= 16:
            return short_ip, version_text
    return ip, version_text


# ---------------------------------------------------------------------------
# Run control
# ---------------------------------------------------------------------------
#region
def _stop_relay_for_current_zone(relay, state):
    if state.current_zone_id:
        relay.off(state.current_zone_id)


async def start_run(relay, state, zone_id, duration_seconds, mode):
    """Start a zone. If another zone is running, stop it first.
    Returns False without touching state if zone_id isn't a configured/
    enabled relay -- otherwise state/the API would claim a run that never
    physically started (relay.on() would have silently no-op'd)."""
    if not relay.is_zone_configured(zone_id):
        print("Run request rejected: zone {} not configured/enabled".format(zone_id))
        return False
    if state.is_running():
        _stop_relay_for_current_zone(relay, state)
    now_epoch = unix_time()
    relay.on(zone_id)
    state.start_run(now_epoch, duration_seconds, mode, zone_id)
    print("Run started: zone={} mode={} duration={}s".format(zone_id, mode, duration_seconds))
    return True


async def stop_run(relay, state, config, status_writer, status_str="completed"):
    if not state.is_running():
        relay.all_off()
        return
    start_epoch = state.current_run_start_epoch
    mode        = state.current_run_mode
    zone_id     = state.current_zone_id
    end_epoch   = unix_time()

    _stop_relay_for_current_zone(relay, state)
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
            await status_writer.push_last_run(start_epoch, end_epoch, mode, zone_id, status_str)
        except Exception as ex:
            print("Firebase push_last_run failed (non-fatal):", ex)
#endregion

# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------
#region
async def local_control_loop(relay, state, config, tz_name, last_run_slots,
                              lcd_status, local_ip_holder, local_override,
                              override_reader, status_writer, relay_stop_fn):
    """Fast local loop: stop-check, scheduler, LCD refresh. Nothing here
    is Firebase-dependent except the fail-open override read, which only
    happens the instant a slot is about to fire -- not every tick."""
    while True:
        try:
            now_epoch   = unix_time()
            local_epoch = local_wall_clock_epoch(now_epoch, tz_name)
            now_tuple   = time.gmtime(local_epoch)
            now_date_string = "{:04d}-{:02d}-{:02d}".format(*now_tuple[:3])

            # --- Stop check ---
            if state.should_stop_now(now_epoch):
                await relay_stop_fn("completed")

            # --- Scheduler ---
            if not state.is_running():
                clear_old_slot_runs(last_run_slots, local_epoch)

                slot, slot_key = get_pending_slot(
                    config.get("schedule", {}), state, last_run_slots, local_epoch)

                if slot and slot_key:
                    skip_active = local_override["skip_today"]
                    skip_reason = local_override["skip_reason"]
                    if not skip_active:
                        try:
                            skip_active, skip_reason = await override_reader.get_active_skip(now_date_string)
                        except Exception as ex:
                            print("Override read error (fail open):", ex)
                            skip_active = False

                    if skip_active:
                        print("Scheduled slot skipped:", slot_key, "reason:", skip_reason)
                        last_run_slots[slot_key] = local_epoch
                    else:
                        zone_id          = slot.get("zone", 1)
                        duration_seconds = slot.get("duration_minutes", 10) * 60
                        await start_run(relay, state, zone_id, duration_seconds, "scheduled")
                        last_run_slots[slot_key] = local_epoch

            # --- LCD status refresh ---
            if lcd_status:
                zone_text = ("Zone {}".format(state.current_zone_id)
                             if state.is_running() else "Idle")
                next_slot = get_next_slot(config.get("schedule", {}), last_run_slots, local_epoch)
                if next_slot:
                    next_day, next_hour, next_minute, _next_zone = next_slot
                    day_abbr = next_day[:3]
                    day_abbr = day_abbr[0].upper() + day_abbr[1:]
                    next_text = "Next: {} {:02d}:{:02d}".format(day_abbr, next_hour, next_minute)
                else:
                    next_text = "No sched"
                ip_text, version_text = _format_ip_version(local_ip_holder["ip"], FIRMWARE_VERSION)
                lcd_status.show_status(zone_text, next_text, ip_text, version_text)

        except Exception as ex:
            print("local_control_loop error:", ex)
            relay.all_off()
            if lcd_status:
                try:
                    lcd_status.show_message("ERR: {}".format(ex))
                except Exception:
                    pass

        await asyncio.sleep(LOCAL_TICK_INTERVAL)


async def status_sync_loop(status_writer, local_override, override_reader,
                            status_led, fb):
    """Own cadence, independent of everything else -- this is the one that
    was batched into the Pico's 15-min pass; now it just runs on its own
    real interval."""
    while True:
        await asyncio.sleep(STATUS_SYNC_INTERVAL)
        try:
            skip_active = local_override["skip_today"]
            skip_reason = local_override["skip_reason"]
            if not skip_active:
                try:
                    now_date_string = time.strftime("%Y-%m-%d", time.gmtime(unix_time()))
                    skip_active, skip_reason = await override_reader.get_active_skip(now_date_string)
                except Exception as ex:
                    print("Override read for status display failed (non-fatal):", ex)

            await status_writer.push_status(active_skip=skip_active, active_skip_reason=skip_reason)
            status_led.set_mode("running")
        except Exception as ex:
            print("Firebase status push failed (non-fatal):", ex)
            status_led.set_mode("no_internet")


async def meta_sync_loop(status_writer, schedule_sync, local_ip_holder):
    """Zones/schedule/IP -- these change rarely, so a slower cadence than
    the status push is fine."""
    while True:
        await asyncio.sleep(META_SYNC_INTERVAL)
        try:
            current_ip = local_ip()
            if current_ip != "0.0.0.0":
                local_ip_holder["ip"] = current_ip
                await status_writer.push_ip(current_ip)
        except Exception as ex:
            print("Firebase push_ip failed (non-fatal):", ex)

        try:
            await schedule_sync.push_zones()
        except Exception as ex:
            print("Schedule sync (zones) push failed (non-fatal):", ex)

        try:
            await schedule_sync.push_schedule()
        except Exception as ex:
            print("Schedule sync (schedule) push failed (non-fatal):", ex)


async def rtc_mirror_loop(rtc):
    while True:
        await asyncio.sleep(RTC_MIRROR_INTERVAL)
        mirror_system_clock_to_rtc(rtc)


async def resync_trigger_loop(rtc, local_resync_trigger):
    """Services the /resync-time endpoint's immediate-trigger flag on a
    tight poll, separate from rtc_mirror_loop's slow automatic cadence."""
    while True:
        await asyncio.sleep(1)
        if local_resync_trigger["requested"]:
            local_resync_trigger["requested"] = False
            mirror_system_clock_to_rtc(rtc)
            print("RTC: resynced (manual trigger)")


async def update_loop(fb, state):
    """
    Polls Firebase's update node every UPDATE_POLL_INTERVAL for either an
    "Update Now" tap (apply_requested) or a "Check Now" tap (requested),
    and otherwise runs a real version check on its own UPDATE_CHECK_INTERVAL
    cadence. No push notifications yet -- the app reads this same node to
    show an "update available" badge and drives everything from there.

    An apply is deferred (not lost) if a zone is currently running --
    re-checked next poll instead of interrupting an active irrigation run.
    Applying a version successfully ends the process (sys.exit) so
    systemd's Restart=always relaunches it running the newly checked-out
    code; a failed checkout just reports the error and stays on the
    current version.
    """
    last_version_check = 0
    while True:
        await asyncio.sleep(UPDATE_POLL_INTERVAL)
        try:
            update_node = await fb.get("update") or {}
        except Exception as ex:
            print("Update: Firebase read failed (non-fatal):", ex)
            continue

        now = unix_time()

        if update_node.get("apply_requested"):
            available_version = update_node.get("available_version")
            if not available_version:
                print("Update: apply_requested with no available_version on file -- clearing")
                await fb.patch("update", {"apply_requested": False})
                continue
            if state.is_running():
                print("Update: apply requested but a zone is currently running -- deferring")
                continue
            print("Update: applying", available_version)
            await fb.patch("update", {"status": "applying",
                                        "message": "Applying update..."})
            ok, err = update_checker.apply_update(available_version)
            if ok:
                print("Update: checked out", available_version, "-- restarting")
                await fb.patch("update", {
                    "status": "idle", "apply_requested": False,
                    "current_version": available_version, "available_version": None,
                    "message": "Updated to {}".format(available_version),
                })
                sys.exit(0)
            print("Update: checkout failed:", err)
            await fb.patch("update", {"status": "error", "apply_requested": False,
                                        "message": "Update failed: {}".format(err)})
            continue

        due_for_check = (now - last_version_check) >= UPDATE_CHECK_INTERVAL
        if not (due_for_check or update_node.get("requested")):
            continue

        last_version_check = now
        print("Update: checking for new version...")
        await fb.patch("update", {"status": "checking", "requested": False})
        try:
            latest_tag = update_checker.get_latest_tag()
        except Exception as ex:
            print("Update: version check failed (non-fatal):", ex)
            await fb.patch("update", {"status": "error", "message": str(ex)})
            continue

        if latest_tag and update_checker.is_newer(latest_tag, FIRMWARE_VERSION):
            print("Update: available ->", latest_tag)
            await fb.patch("update", {
                "status": "available", "available_version": latest_tag,
                "current_version": FIRMWARE_VERSION, "checked_at": now,
                "message": "Version {} available".format(latest_tag),
            })
        else:
            await fb.patch("update", {
                "status": "idle", "available_version": None,
                "current_version": FIRMWARE_VERSION, "checked_at": now,
                "message": "Up to date at {}".format(FIRMWARE_VERSION),
            })


# ---------------------------------------------------------------------------
# Boot
# ---------------------------------------------------------------------------
#region
async def main():
    config  = load_config()
    state   = ControllerState()
    tz_name = config.get("timezone", "UTC")

    relay = ZoneRelayController(
        zones_config=config.get("zones", []),
        active_high=config.get("relay_active_high", True),
    )
    relay.all_off()   # SAFETY: de-energise all relays before anything else

    status_led = StatusLED(green_pin=23, red_pin=24)   # physical 16, 18
    status_led.set_mode("booting")

    # =======================================================================
    # ========== LCD
    # =======================================================================

    # LCD is non-fatal -- an unwired/broken backpack shouldn't take the
    # whole controller down, it just means no display. Talks to the
    # backpack's MCP23008 over I2C bus 3 -- a software (bit-banged) I2C
    # bus on GPIO27/GPIO17 (dtoverlay=i2c-gpio in /boot/firmware/config.txt),
    # matching this board's existing DAT/CLK terminal-block wiring rather
    # than the Pi's dedicated hardware I2C1 bus (which the DS3231 below
    # uses instead, on GPIO2/GPIO3).
    from smbus2 import SMBus

    lcd_status = None
    try:
        lcd_bus = SMBus(3)
        lcd = LCD1602(lcd_bus)
        lcd_status = LCDStatus(lcd)
        lcd_status.show_message("Booting")
        print("LCD: initialized OK")
    except Exception as ex:
        print("LCD init failed (not wired?):", ex)

    # =======================================================================
    # ========== RTC
    # =======================================================================
    rtc = None
    try:
        bus = SMBus(1)   # /dev/i2c-1, the Pi's user-facing I2C bus (GPIO2/GPIO3)
        rtc = DS3231(bus)
        rtc.datetime_tuple()   # probe
        print("RTC: initialized OK")
    except Exception as ex:
        print("RTC init failed (not wired?):", ex)
        rtc = None

    seed_system_clock_from_rtc(rtc)

    # =======================================================================
    # ========== Network
    # =======================================================================
    last_run_slots  = {}
    local_ip_holder = {"ip": local_ip()}

    boot_log = {
        "firmware_version": FIRMWARE_VERSION,
        "zones_configured": relay.zone_ids(),
        "lcd_present":      lcd_status is not None,
        "rtc_present":      rtc is not None,
        "local_ip":         local_ip_holder["ip"],
    }

    boot_log["network_reachable"] = await network_reachable()

    # =======================================================================
    # ========== Firebase
    # =======================================================================
    fb = FirebaseClient(
        api_key=FIREBASE_API_KEY, email=FIREBASE_EMAIL,
        password=FIREBASE_PASSWORD, db_url=FIREBASE_DB_URL,
        device_id=FIREBASE_DEVICE_ID,
    )
    firebase_ok = False
    try:
        firebase_ok = await fb.authenticate()
    except Exception as ex:
        print("Firebase auth failed (non-fatal):", ex)
    if not firebase_ok:
        await asyncio.sleep(1.5)
        try:
            firebase_ok = await fb.authenticate()
        except Exception as ex:
            print("Firebase auth retry failed (non-fatal):", ex)
    boot_log["firebase_auth_ok"]    = firebase_ok
    boot_log["firebase_auth_error"] = None if firebase_ok else fb.last_auth_error

    import device_secrets
    expected_uid = getattr(device_secrets, "FIREBASE_EXPECTED_UID", None)
    boot_log["firebase_uid"] = fb.uid
    boot_log["expected_uid_mismatch"] = bool(
        firebase_ok and expected_uid and fb.uid != expected_uid)
    if boot_log["expected_uid_mismatch"]:
        print("Firebase: WARNING authenticated UID {} != FIREBASE_EXPECTED_UID {} "
              "in device_secrets.py -- wrong device credentials for this "
              "board?".format(fb.uid, expected_uid))

    boot_log["device_owner_uid_claimed"] = None
    if firebase_ok:
        try:
            boot_log["device_owner_uid_claimed"] = await fb.put("device_owner_uid", fb.uid)
            if not boot_log["device_owner_uid_claimed"]:
                print("Firebase: device_owner_uid claim failed -- this device_id "
                      "may already be owned by a different account.")
                if lcd_status:
                    lcd_status.show_message("ID already used")
        except Exception as ex:
            print("Firebase: device_owner_uid claim exception (non-fatal):", ex)

    status_writer   = StatusWriter(fb, state, config, FIRMWARE_VERSION,
                                    config.get("device_name", "LetItRain Controller"))
    override_reader = OverrideReader(fb)
    schedule_sync   = ScheduleSync(fb, config)

    if firebase_ok:
        try:
            await schedule_sync.push()
            await status_writer.push_ip(local_ip_holder["ip"])
            status_led.set_mode("running")
        except Exception as ex:
            print("Firebase boot sync failed (non-fatal):", ex)
            status_led.set_mode("no_internet")
    else:
        status_led.set_mode("no_internet")

    _write_boot_log(boot_log)
    print("LetItRain v{} booting... boot_log={}".format(FIRMWARE_VERSION, boot_log))

    # =======================================================================
    # ========== HTTP API + callbacks
    # =======================================================================

    local_override       = {"skip_today": False, "skip_reason": None}
    local_resync_trigger = {"requested": False}

    async def on_manual_start(zone_id=1, duration_minutes=None):
        mins = duration_minutes or config.get("manual_default_duration_minutes", 10)
        return await start_run(relay, state, int(zone_id), int(mins) * 60, "manual")

    async def on_manual_stop():
        await stop_run(relay, state, config, status_writer, "manual_stop")

    async def relay_stop_fn(status_str):
        await stop_run(relay, state, config, status_writer, status_str)

    async def on_config_saved(changed_keys):
        """Fires after every successful /config save. Rebuilds the relay's
        live pin map immediately when zones change (otherwise the change
        only lands in config.json and never takes effect until the process
        restarts -- see hardware/relay.py's reconfigure()), and pushes
        zones/schedule to Firebase immediately rather than waiting for
        meta_sync_loop's next 300s cycle -- otherwise a save followed by
        closing the app (or the process restarting) before that cycle
        fires means Firebase, and therefore the app's remote/cold-launch
        view, silently shows a stale pre-edit copy with no indication
        anything is out of date."""
        if "zones" in changed_keys:
            relay.reconfigure(config.get("zones", []))
            try:
                await schedule_sync.push_zones()
            except Exception as ex:
                print("Immediate zones push after /config save failed (non-fatal):", ex)
        if "schedule" in changed_keys:
            try:
                await schedule_sync.push_schedule()
            except Exception as ex:
                print("Immediate schedule push after /config save failed (non-fatal):", ex)

    app = create_app(
        config=config, state=state, rtc=rtc,
        on_manual_start=on_manual_start, on_manual_stop=on_manual_stop,
        on_config_saved=on_config_saved,
        local_override=local_override, local_resync_trigger=local_resync_trigger,
        save_config_fn=save_config, now_fn=unix_time,
        firmware_version=FIRMWARE_VERSION,
    )
    uv_config = uvicorn.Config(app, host="0.0.0.0", port=80, log_level="info")
    server = uvicorn.Server(uv_config)

    # =======================================================================
    # ========== Main tasks
    # =======================================================================
    print("Main tasks starting.")
    try:
        await asyncio.gather(
            server.serve(),
            local_control_loop(relay, state, config, tz_name, last_run_slots,
                                lcd_status, local_ip_holder, local_override,
                                override_reader, status_writer, relay_stop_fn),
            status_sync_loop(status_writer, local_override, override_reader, status_led, fb),
            meta_sync_loop(status_writer, schedule_sync, local_ip_holder),
            rtc_mirror_loop(rtc),
            resync_trigger_loop(rtc, local_resync_trigger),
            update_loop(fb, state),
            watchdog_loop(),
        )
    finally:
        relay.all_off()
        status_led.set_mode("boot_failed")
        try:
            await status_writer.push_offline()
        except Exception:
            pass
        await fb.aclose()
#endregion

if __name__ == "__main__":
    asyncio.run(main())
