import utime
from machine import I2C, Pin
import ntptime

from secrets import WIFI_SSID, WIFI_PASSWORD
from hardware.relay import RelayController
from hardware.ds3231 import DS3231
from storage.config_store import load_config, save_config
from core.state import ControllerState
from core.scheduler import should_start_now, should_stop_now
from web.server import connect_wifi, run_server
from update.updater import check_for_update


config = load_config()
state = ControllerState()

relay = RelayController(
    pin_number=config.get("relay_pin", 15),
    active_high=config.get("relay_active_high", True),
)
relay.off()  # safe startup state

## TODO - Bring these values back when you install clock
i2c = I2C(0, sda=Pin(0), scl=Pin(1), freq=100000)
rtc = DS3231(i2c)

## Helper functions to handle when clock doesn't exist
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

# Function to sync clock
def sync_rtc_from_ntp():
    if rtc is None:
        raise RuntimeError("RTC not initialized")

    ntptime.settime()
    t = utime.localtime(utime.time() - 5 * 3600)  # EST
    year = t[0]
    month = t[1]
    day = t[2]
    hour = t[3]
    minute = t[4]
    second = t[5]
    weekday = t[6] + 1

    rtc.set_datetime(year, month, day, hour, minute, second, weekday)
    return rtc.iso_string()



def persist_last_run(start_epoch, end_epoch, mode, status):
    config["last_run"] = {
        "start_epoch": start_epoch,
        "end_epoch": end_epoch,
        "mode": mode,
        "status": status,
    }
    save_config(config)

def start_run(duration_seconds, mode):
    if state.is_running():
        return

    now_epoch = get_now_epoch()
    relay.on()
    state.start_run(now_epoch, duration_seconds, mode)
    print("Run started:", mode, "for", duration_seconds, "seconds at", get_now_iso())

def stop_run(status="completed"):
    if not state.is_running():
        relay.off()
        return

    start_epoch = state.current_run_start_epoch
    mode = state.current_run_mode
    end_epoch = get_now_epoch()

    relay.off()
    state.stop_run()
    persist_last_run(start_epoch, end_epoch, mode, status)
    print("Run stopped:", status, "at", get_now_iso())

def on_manual_start():
    minutes = config.get("manual_default_duration_minutes", 30)
    start_run(minutes * 60, "manual")

def on_manual_stop():
    stop_run("manual_stop")

def start_web_server():
    try:
        wlan = connect_wifi(WIFI_SSID, WIFI_PASSWORD)
        print("Wi-Fi connected:", wlan.ifconfig())
        run_server(config, state, rtc, on_manual_start, on_manual_stop, sync_rtc_from_ntp)
    
    except Exception as ex:
        print("Web server unavailable:", ex)

def main():
    print("Booting sprinkler controller...")

    # Try to start networking once.
    # If it fails, the scheduler still runs.
    try:
        import _thread
        _thread.start_new_thread(start_web_server, ())
    except Exception as ex:
        print("Thread start failed:", ex)
        print("Attempting web server on main loop later is skipped; scheduler will still run.")

    while True:
        try:
            try:
                now_epoch = get_now_epoch()
            except Exception as ex:
                print("RTC read failed in scheduler:", ex)
                utime.sleep(5)
                continue

            last_run_start = config.get("last_run", {}).get("start_epoch")
            schedule = config.get("schedule", {})

            if should_start_now(schedule, now_epoch, state, last_run_start):
                duration_seconds = schedule.get("duration_minutes", 10) * 60
                start_run(duration_seconds, "scheduled")

            if should_stop_now(now_epoch, state):
                stop_run("completed")

        except Exception as ex:
            print("Main loop error:", ex)
            relay.off()

        utime.sleep(5)

main()
