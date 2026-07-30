# hardware/status_led.py
# Dual-color status LED, driven by explicit polling (call .tick() often)
# -- same polling design as the MicroPython build, now driven by an
# asyncio task in main.py instead of the main loop's manual tick loop.
#
# Modes:
#   "booting"     green flashes on 3s / off 1s   red off
#   "running"     green solid on                  red off
#   "no_internet" green solid on                   red flashes on 5s / off 2s
#   "boot_failed" green off                        red flashes rapidly, on 150ms / off 150ms

import time
from gpiozero import OutputDevice

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
        self._green = OutputDevice(green_pin)
        self._red   = OutputDevice(red_pin)
        self._green.off()
        self._red.off()

        self._mode            = None
        self._mode_started    = time.monotonic()

    def set_mode(self, mode):
        if mode not in _PATTERNS:
            raise ValueError("Unknown LED mode: {}".format(mode))
        if mode != self._mode:
            self._mode         = mode
            self._mode_started = time.monotonic()
            self.tick()   # apply immediately so solid on/off modes show right away

    def tick(self):
        """Re-evaluate LED state against elapsed time. Call this frequently."""
        pattern = _PATTERNS.get(self._mode)
        if not pattern:
            return
        elapsed_ms = (time.monotonic() - self._mode_started) * 1000
        self._apply(self._green, pattern["green"], elapsed_ms)
        self._apply(self._red, pattern["red"], elapsed_ms)

    @staticmethod
    def _apply(device, spec, elapsed_ms):
        if spec is True:
            device.on()
        elif spec is False or spec is None:
            device.off()
        else:
            on_ms, off_ms = spec
            if (elapsed_ms % (on_ms + off_ms)) < on_ms:
                device.on()
            else:
                device.off()
