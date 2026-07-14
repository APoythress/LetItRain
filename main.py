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
import _thread
from machine import I2C, Pin, reset

from secrets import (
    WIFI_SSID, WIFI_PASSWORD,
    FIREBASE_API_KEY, FIREBASE_EMAIL, FIREBASE_PASSWORD,
    FIREBASE_DB_URL, FIREBASE_DEVICE_ID, FIREBASE_STORAGE_BUCKET,
    FIRMWARE_VERSION,
)

from netcfg.wifi import connect_wifi

from hardware.relay       import ZoneRelayController
from hardware.ds3231      import DS3231
from hardware.status_led  import StatusLED
from storage.config_store import load_config, save_config
from core.state           import ControllerState
from core.scheduler       import get_pending_slot, clear_old_slot_runs
from core.unix_time       import unix_time, to_unix

from firebase.client      import FirebaseClient
from firebase.status_writer  import StatusWriter
from firebase.override_reader import OverrideReader
from firebase.schedule_sync  import ScheduleSync
from web.server           import run_server
from update.updater       import check_for_update, get_status as get_ota_status

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
    while True:
        _failed_led.tick()
        utime.sleep_ms(50)

# Tracks which schedule slots have already fired today: {"monday_0": epoch, ...}
last_run_slots = {}

# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def get_now_epoch():
    if rtc:
        return to_unix(rtc.epoch())
    return unix_time()


def get_now_date_string():
    """Return today's date as 'YYYY-MM-DD' for skip-date comparisons."""
    if rtc:
        iso = rtc.iso_string()
        return iso[:10]
    t = utime.localtime()
    return "{:04d}-{:02d}-{:02d}".format(t[0], t[1], t[2])


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
            firmware_version=FIRMWARE_VERSION,
        )
    except Exception as ex:
        print("HTTP server thread crashed:", ex)


# ---------------------------------------------------------------------------
# Module-level reference so stop_run() can call status_writer
# ---------------------------------------------------------------------------

status_writer   = None
override_reader = None
schedule_sync   = None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    global status_writer, override_reader, schedule_sync

    print("LetItRain v{} booting...".format(FIRMWARE_VERSION))
    print("Zones configured:", relay.zone_ids())

    # --- Wi-Fi ---
    local_ip = "0.0.0.0"
    try:
        wlan = connect_wifi(WIFI_SSID, WIFI_PASSWORD, on_wait=status_led.tick)
        local_ip = wlan.ifconfig()[0]
    except Exception as ex:
        print("Wi-Fi failed (non-fatal, running offline):", ex)

    # --- NTP time sync ---
    # Without this, utime.time() stays at its arbitrary boot-time default
    # instead of the real date, and every timestamp sent to Firebase/the
    # app (heartbeats, run times) will be meaningless.
    try:
        import ntptime
        ntptime.settime()
        print("NTP: time synced")
    except Exception as ex:
        print("NTP: sync failed (non-fatal):", ex)

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

    status_writer   = StatusWriter(fb, state, config, FIRMWARE_VERSION,
                                   config.get("device_name", "LetItRain Controller"))
    override_reader = OverrideReader(fb)
    schedule_sync   = ScheduleSync(fb, config, save_config)

    update_pending = False

    if firebase_ok:
        try:
            schedule_sync.push_initial()   # seed Firebase if empty
            schedule_sync.sync()           # pull latest schedule/zones
            status_writer.push_ip(local_ip)
            status_led.set_mode("running")
        except Exception as ex:
            print("Firebase boot sync failed (non-fatal):", ex)
            status_led.set_mode("no_internet")

        try:
            update_pending = check_for_update(FIREBASE_STORAGE_BUCKET, fb.id_token)
        except Exception as ex:
            print("OTA update check failed (non-fatal):", ex)
    else:
        status_led.set_mode("no_internet")

    # --- HTTP server thread ---
    try:
        _thread.start_new_thread(start_web_server, ())
    except Exception as ex:
        print("HTTP thread start failed:", ex)

    # --- Timing ---
    last_status_push  = 0
    last_schedule_sync = 0
    last_update_check  = utime.time()
    STATUS_INTERVAL   = 15
    SYNC_INTERVAL     = 60
    UPDATE_CHECK_INTERVAL = 21600  # 6 hours

    print("Main loop started.")

    try:
        while True:
            try:
                now_epoch       = get_now_epoch()
                now_date_string = get_now_date_string()

                # --- Stop check ---
                if state.should_stop_now(now_epoch):
                    stop_run("completed")

                # --- Scheduler ---
                if not state.is_running():
                    clear_old_slot_runs(last_run_slots, now_epoch)

                    slot, slot_key = get_pending_slot(
                        config.get("schedule", {}),
                        state,
                        last_run_slots,
                        now_epoch,
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
                            last_run_slots[slot_key] = now_epoch  # mark as handled
                            # FUTURE v1.2: rain_inches threshold check here
                        else:
                            zone_id          = slot.get("zone", 1)
                            duration_seconds = slot.get("duration_minutes", 10) * 60
                            start_run(zone_id, duration_seconds, "scheduled")
                            last_run_slots[slot_key] = now_epoch

                # --- Firebase heartbeat ---
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

                    # Manual OTA trigger from the app: devices/{id}/update/requested
                    if not update_pending and fb.id_token:
                        try:
                            update_info = fb.get("update") or {}
                            if update_info.get("requested"):
                                fb.patch("update", {"requested": False})  # clear so it fires once
                                update_pending = check_for_update(FIREBASE_STORAGE_BUCKET, fb.id_token)
                        except Exception as ex:
                            print("OTA trigger check failed (non-fatal):", ex)

                    # Publish current OTA status so the app can show progress
                    try:
                        fb.patch("update", get_ota_status())
                    except Exception:
                        pass

                    last_status_push = utime.time()

                # --- Schedule sync ---
                if utime.time() - last_schedule_sync >= SYNC_INTERVAL:
                    try:
                        schedule_sync.sync()
                        # If zones changed, re-init relay controller would need reboot
                        # For now: log a note; zone hardware changes require reboot
                    except Exception as ex:
                        print("Schedule sync failed (non-fatal):", ex)
                    last_schedule_sync = utime.time()

                # --- OTA update check ---
                if not update_pending and utime.time() - last_update_check >= UPDATE_CHECK_INTERVAL:
                    if fb.id_token:
                        try:
                            update_pending = check_for_update(FIREBASE_STORAGE_BUCKET, fb.id_token)
                        except Exception as ex:
                            print("OTA update check failed (non-fatal):", ex)
                    last_update_check = utime.time()

                # An update was downloaded and is staged — apply it as soon as
                # no zone is actively running, so a reboot never cuts a run short.
                if update_pending and not state.is_running():
                    print("OTA: applying staged update, rebooting...")
                    relay.all_off()
                    reset()

            except Exception as ex:
                print("Main loop error:", ex)
                relay.all_off()

            # Tick the LED every 100ms during the 5s pause so its pattern
            # stays accurate instead of only updating once per loop pass.
            for _ in range(50):
                status_led.tick()
                utime.sleep_ms(100)

    finally:
        relay.all_off()
        status_led.set_mode("boot_failed")
        try:
            status_writer.push_offline()
        except Exception:
            pass


main()
