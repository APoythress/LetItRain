# core/mem_diag.py
# Tracks the lowest gc.mem_free() value observed since boot.
#
# Sampled at the highest memory-pressure points (right after a socket
# response is closed but before that call site's own gc.collect() cleans
# it back up) rather than once per main-loop pass, so the number reflects
# the tightest moment the heap actually reached instead of the resting
# value between operations. This is the number that answers "how close
# to OOM has this board actually gotten" over real uptime, without
# needing a serial console attached the whole time.

import gc

_min_free = None


def sample():
    """Record the current free-heap reading if it's a new low."""
    global _min_free
    free = gc.mem_free()
    if _min_free is None or free < _min_free:
        _min_free = free
    return free


def min_free():
    """Lowest gc.mem_free() seen since boot, or None if never sampled."""
    return _min_free


def heap_total():
    """Approximate total heap size in bytes (constant for the process's
    lifetime on MicroPython -- the arena size is fixed at boot)."""
    return gc.mem_free() + gc.mem_alloc()
