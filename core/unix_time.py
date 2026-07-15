# core/unix_time.py
# On this board's MicroPython build (v1.25.0, rp2), utime.time() already
# returns real Unix (1970-01-01) seconds once ntptime.settime() has run at
# boot -- confirmed empirically (a 2000-epoch offset here overshot the app's
# Date(timeIntervalSince1970:) math by ~30 years). Kept as a named module
# rather than calling utime.time() directly everywhere, so if a future board
# or firmware build needs a real conversion, there's one place to add it.

import utime


def unix_time():
    """Current time as real Unix seconds (for Firebase/app-facing timestamps)."""
    return utime.time()


def to_unix(mp_epoch):
    """Pass-through today; kept for symmetry with unix_time() and DS3231.epoch()."""
    return mp_epoch
