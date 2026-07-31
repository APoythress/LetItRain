# core/unix_time.py
# Time helpers for CPython/Linux. Replaces the Pico build's hardcoded
# "-5 EST, no DST" offset with a real IANA timezone via zoneinfo (stdlib
# since Python 3.9) -- DST transitions are now handled correctly instead
# of silently drifting an hour twice a year.
#
# local_wall_clock_epoch() keeps the same "shifted epoch" trick the old
# MicroPython code used (main.py's get_local_wall_clock_epoch() + utime's
# tz-naive localtime()) so core/scheduler.py's slot-matching logic can stay
# completely unchanged -- it still just calls time.gmtime() on a shifted
# epoch and reads out hour/minute/weekday. The only thing that changes is
# *how* the shift amount is computed: dynamically per-instant via zoneinfo
# (correct across DST) instead of a fixed constant.

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def unix_time():
    """Current true UTC epoch (int seconds) -- for Firebase/app-facing
    timestamps and run-duration math."""
    return int(datetime.now(timezone.utc).timestamp())


def local_wall_clock_epoch(utc_epoch, tz_name):
    """Return a shifted epoch such that time.gmtime()/time.localtime() on
    it yields local wall-clock fields (hour/minute/weekday) for tz_name at
    this instant -- including the correct DST offset, unlike a fixed
    constant. Never send this value to Firebase/the app; it is not a real
    timestamp, only a field-extraction convenience for the scheduler and
    the LCD's "next run" display.
    """
    aware = datetime.fromtimestamp(utc_epoch, tz=ZoneInfo(tz_name))
    naive_as_utc = aware.replace(tzinfo=timezone.utc)
    return int(naive_as_utc.timestamp())
