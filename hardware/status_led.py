# hardware/status_led.py
# Dual-color status LED, driven by explicit polling (call .tick() often)
# rather than machine.Timer — timer callbacks were not firing reliably
# alongside the _thread-based HTTP server on this board/firmware.
#
# Modes:
#   "booting"     green flashes on 3s / off 1s   red off
#   "running"     green solid on                  red off
#   "no_internet" green solid on                   red flashes on 5s / off 2s
#   "boot_failed" green off                        red flashes rapidly, on 150ms / off 150ms

import utime
from machine import Pin

# (on_ms, off_ms) per LED per mode. True = solid on, False/None = off.
_PATTERNS = {
    "booting":     {"green": (500, 500), "red": False},
    "running":     {"green": True,         "red": False},
    "no_internet": {"green": True,         "red": (5000, 2000)},
    "boot_failed": {"green": False,        "red": (150, 150)},
}


class StatusLED:
    """
    Usage:
        status_led = StatusLED(green_pin=16, red_pin=17)
        status_led.set_mode("booting")
        ...
        status_led.tick()   # call at least every ~100ms for accurate patterns
    """

    def __init__(self, green_pin, red_pin):
        self._green = Pin(green_pin, Pin.OUT)
        self._red   = Pin(red_pin, Pin.OUT)
        self._green.value(0)
        self._red.value(0)

        self._mode            = None
        self._mode_started_ms = utime.ticks_ms()

    def set_mode(self, mode):
        if mode not in _PATTERNS:
            raise ValueError("Unknown LED mode: {}".format(mode))
        if mode != self._mode:
            self._mode            = mode
            self._mode_started_ms = utime.ticks_ms()
            self.tick()   # apply immediately so solid on/off modes show right away

    def tick(self):
        """Re-evaluate LED state against elapsed time. Call this frequently."""
        pattern = _PATTERNS.get(self._mode)
        if not pattern:
            return
        elapsed = utime.ticks_diff(utime.ticks_ms(), self._mode_started_ms)
        self._apply(self._green, pattern["green"], elapsed)
        self._apply(self._red, pattern["red"], elapsed)

    @staticmethod
    def _apply(pin, spec, elapsed_ms):
        if spec is True:
            pin.value(1)
        elif spec is False or spec is None:
            pin.value(0)
        else:
            on_ms, off_ms = spec
            pin.value(1 if (elapsed_ms % (on_ms + off_ms)) < on_ms else 0)
