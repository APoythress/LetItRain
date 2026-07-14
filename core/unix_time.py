# core/unix_time.py
# MicroPython's utime epoch on this port is 2000-01-01, not 1970-01-01
# like Unix/the iOS app's Date(timeIntervalSince1970:). Any timestamp
# handed to Firebase/the app must be converted, or "last seen" and run
# timestamps will be off by ~30 years and read as permanently stale.

import utime

_UNIX_EPOCH_OFFSET = 946684800  # seconds between 1970-01-01 and 2000-01-01


def unix_time():
    """Current time as real Unix seconds (for Firebase/app-facing timestamps)."""
    return utime.time() + _UNIX_EPOCH_OFFSET


def to_unix(mp_epoch):
    """Convert a MicroPython-epoch value (e.g. from DS3231.epoch()) to Unix seconds."""
    return mp_epoch + _UNIX_EPOCH_OFFSET
