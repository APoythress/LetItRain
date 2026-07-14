# main.py
# LetItRain Sprinkler Controller — v1.1.0
#
# Architecture:
#   - HTTP JSON server (background thread) for local iOS app control
#   - Firebase Realtime Database writer for remote status visibility
#   - Firebase override reader for remote "skip today" support
#   - Existing scheduler and relay logic unchanged
#
# Mode summary:
#   Local  — iOS app talks directly to this HTTP server (full control)
#   Remote — iOS app reads Firebase status (read-only + skip-today write)

import utime
import _thread
from machine import I2C, Pin

import ntptime

from secrets import (
    WIFI_SSID, WIFI_PASSWORD,
    FIREBASE_API_KEY, FIREBASE_EMAIL, FIREBASE_PASSWORD,
    FIREBASE_DB_URL, FIREBASE_DEVICE_ID,
    FIRMWARE_VERSION,
)

from hardware.relay       import RelayController
from hardware.ds3231      import DS3231
from storage.config_store import load_config, save_config
from core.state           import ControllerState
from core.scheduler       import should_start_now, should_stop_now
from network.wifi         import connect_wifi
from firebase.client      import FirebaseClient
from firebase.status_writer  import StatusWriter
from firebase.override_reader import OverrideReader
from web.server           import run_server

# ---------------------------------------------------------------------------
# Boot — hardware init
# relay.off() MUST be the first hardware operation. Do not move it.
# ---------------------------------------------------------------------------

config = load_config()
state  = ControllerState()

relay = RelayController(
    pin_number=config.get("relay_pin", 15),
    active_high=config.get("relay_active_high", True),
)
relay.off()  # ← SAFETY: ensure relay is off on every boot

i2c = I2C(0, sda=Pin(0), scl=Pin(1), freq=100000)
rtc = DS3231(i2c)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_now_epoch():
    if rtc is not None:
        return rtc.epoch()
    return utime.time()


def get_now_iso():
    if rtc is not None:
        return rtc.iso_string()
    t = utime.localtime()
    return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
        t[0], t[1], t[2], t[3], t[4], t[5]
    )


def get_now_date_string():
    """Return today's date as 'YYYY-MM-DD' for skip-date comparisons."""
    if rtc is not None:
        iso = rtc.iso_string()          # "YYYY-MM-DD HH:MM:SS"
        return iso[:10]
    t = utime.localtime()
    return "{:04d}-{:02d}-{:02d}".format(t[0], t[1], t[2])


def sync_rtc_from_ntp():
    if rtc is None:
        raise RuntimeError("RTC not initialized")
    ntptime.settime()
    t = utime.localtime(utime.time() - 5 * 3600)  # EST offset
    rtc.set_datetime(t[0], t[1], t[2], t[3], t[4], t[5], t[6] + 1)
    return rtc.iso_string()


def persist_last_run(start_epoch, end_epoch, mode, status):
    config["last_run"] = {
        "start_epoch": start_epoch,
        "end_epoch":   end_epoch,
        "mode":        mode,
        "status":      status,
    }
    save_config(config)


# ---------------------------------------------------------------------------
# Run control — callbacks used by HTTP server and scheduler
# ---------------------------------------------------------------------------

def start_run(duration_seconds, mode):
    if state.is_running():
        return
    now_epoch = get_now_epoch()
    relay.on()
    state.start_run(now_epoch, duration_seconds, mode)
    print("Run started:", mode, "for", duration_seconds, "s at", get_now_iso())


def stop_run(status_str="completed"):
    if not state.is_running():
        relay.off()
        return
    start_epoch = state.current_run_start_epoch
    mode        = state.current_run_mode
    end_epoch   = get_now_epoch()
    relay.off()
    state.stop_run()
    persist_last_run(start_epoch, end_epoch, mode, status_str)
    print("Run stopped:", status_str, "at", get_now_iso())

    # Immediately push last-run to Firebase (best-effort)
    try:
        status_writer.push_last_run(start_epoch, end_epoch, mode, status_str)
    except Exception as ex:
        print("Firebase push_last_run failed (non-fatal):", ex)


def on_manual_start(duration_minutes=None):
    mins = duration_minutes or config.get("manual_default_duration_minutes", 10)
    start_run(int(mins) * 60, "manual")


def on_manual_stop():
    stop_run("manual_stop")


# ---------------------------------------------------------------------------
# Local override state — shared mutable dict between HTTP thread and main loop
# ---------------------------------------------------------------------------

local_override = {
    "skip_today":  False,
    "skip_reason": None,
}

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
            sync_rtc_from_ntp=sync_rtc_from_ntp,
            local_override=local_override,
            save_config_fn=save_config,
        )
    except Exception as ex:
        print("HTTP server thread error:", ex)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# Declare at module level so stop_run() can reference status_writer
status_writer = None


def main():
    global status_writer

    print("LetItRain v{} booting...".format(FIRMWARE_VERSION))

    # -----------------------------------------------------------------------
    # Wi-Fi
    # -----------------------------------------------------------------------
    local_ip = "0.0.0.0"
    try:
        wlan     = connect_wifi(WIFI_SSID, WIFI_PASSWORD)
        local_ip = wlan.ifconfig()[0]
    except Exception as ex:
        print("Wi-Fi failed:", ex)
        # Scheduler still runs offline; Firebase features disabled

    # -----------------------------------------------------------------------
    # Firebase init
    # -----------------------------------------------------------------------
    fb = FirebaseClient(
        api_key=FIREBASE_API_KEY,
        email=FIREBASE_EMAIL,
        password=FIREBASE_PASSWORD,
        db_url=FIREBASE_DB_URL,
        device_id=FIREBASE_DEVICE_ID,
    )

    firebase_ok = False
    try:
        firebase_ok = fb.authenticate()
    except Exception as ex:
        print("Firebase auth failed (non-fatal):", ex)

    status_writer   = StatusWriter(
        fb, state, config, FIRMWARE_VERSION,
        config.get("device_name", "Pico Sprinkler Controller"),
    )
    override_reader = OverrideReader(fb)

    if firebase_ok:
        try:
            status_writer.push_ip(local_ip)
        except Exception as ex:
            print("Firebase push_ip failed (non-fatal):", ex)

    # -----------------------------------------------------------------------
    # HTTP server in background thread
    # -----------------------------------------------------------------------
    try:
        _thread.start_new_thread(start_web_server, ())
    except Exception as ex:
        print("HTTP server thread failed to start:", ex)

    # -----------------------------------------------------------------------
    # Timing trackers for main loop
    # -----------------------------------------------------------------------
    last_status_push = 0   # push Firebase status every 15s
    STATUS_INTERVAL  = 15

    print("Main loop started.")

    try:
        while True:
            try:
                now_epoch       = get_now_epoch()
                now_date_string = get_now_date_string()

                # -----------------------------------------------------------
                # Scheduler
                # -----------------------------------------------------------
                schedule        = config.get("schedule", {})
                last_run_start  = config.get("last_run", {}).get("start_epoch")

                if should_start_now(schedule, now_epoch, state, last_run_start):
                    # Check local in-memory override first (fastest, no network call)
                    skip_active = local_override["skip_today"]
                    skip_reason = local_override["skip_reason"]

                    # Only query Firebase if local override is not set
                    if not skip_active:
                        try:
                            skip_active, skip_reason = override_reader.get_active_skip(
                                now_date_string
                            )
                        except Exception as ex:
                            print("Override reader error (fail open):", ex)
                            skip_active = False
                            skip_reason = None

                    if skip_active:
                        print("Scheduled run skipped — reason:", skip_reason)
                        # Echo skip into Firebase status
                        # -----------------------------------------------
                        # FUTURE v1.2 — Rain threshold check slot:
                        # Read rain_inches from override_reader result and
                        # compare to config["rain_skip_threshold_inches"].
                        # If below threshold, clear skip_active and proceed.
                        # -----------------------------------------------
                        try:
                            status_writer.push_status(
                                active_skip=True,
                                active_skip_reason=skip_reason,
                            )
                        except Exception:
                            pass
                    else:
                        duration_seconds = schedule.get("duration_minutes", 10) * 60
                        start_run(duration_seconds, "scheduled")

                if should_stop_now(now_epoch, state):
                    stop_run("completed")

                # -----------------------------------------------------------
                # Firebase heartbeat
                # -----------------------------------------------------------
                if utime.time() - last_status_push >= STATUS_INTERVAL:
                    try:
                        status_writer.push_status(
                            active_skip=local_override["skip_today"],
                            active_skip_reason=local_override["skip_reason"],
                        )
                    except Exception as ex:
                        print("Firebase heartbeat failed (non-fatal):", ex)
                    last_status_push = utime.time()

            except Exception as ex:
                print("Main loop error:", ex)
                relay.off()

            utime.sleep(5)

    finally:
        # Best-effort offline marker on clean shutdown
        try:
            status_writer.push_offline()
        except Exception:
            pass


main()
