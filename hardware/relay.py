from machine import Pin

class RelayController:
    def __init__(self, pin_number=15, active_high=True):
        self.pin = Pin(pin_number, Pin.OUT)
        self.active_high = active_high
        self.off()

    def _write(self, on):
        if self.active_high:
            self.pin.value(1 if on else 0)
        else:
            self.pin.value(0 if on else 1)

    def on(self):
        self._write(True)

    def off(self):
        self._write(False)

    def is_on(self):
        raw = self.pin.value()
        return raw == 1 if self.active_high else raw == 0
