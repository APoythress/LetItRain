# hardware/relay.py
# Multi-zone relay controller.
#
# Manages up to 5 relay channels, one per zone.
# Each zone maps to a GPIO pin defined in config["zones"].
#
# Relay boards are typically ACTIVE LOW (relay energises when pin is LOW).
# Set active_high=False if your board energises on LOW (most common for
# mechanical relay hat boards). Set True for solid-state relays.

from machine import Pin


class ZoneRelayController:
    """
    Controls multiple relay channels for multi-zone irrigation.

    Usage:
        controller = ZoneRelayController(zones_config, active_high=False)
        controller.all_off()       # safe state on boot — ALWAYS CALL FIRST
        controller.on(zone_id=1)   # energise zone 1 relay
        controller.off(zone_id=1)  # de-energise zone 1 relay
    """

    def __init__(self, zones_config, active_high=True):
        """
        Args:
            zones_config: list of zone dicts from config["zones"]
                          e.g. [{"id":1,"name":"Front","pin":15,"enabled":true}, ...]
            active_high:  True  → relay energises on HIGH (solid-state relays)
                          False → relay energises on LOW  (mechanical relay boards)
        """
        self._active_high = active_high
        self._pins = {}   # zone_id (int) → Pin

        for zone in zones_config:
            zone_id = zone.get("id")
            pin_num = zone.get("pin")
            enabled = zone.get("enabled", False)
            if zone_id and pin_num is not None and enabled:
                pin = Pin(pin_num, Pin.OUT)
                self._set_pin(pin, False)   # ensure off immediately
                self._pins[zone_id] = pin
                print("Relay: zone {} → GPIO{}".format(zone_id, pin_num))

    def _set_pin(self, pin, energise):
        """Set pin level, respecting active_high polarity."""
        if self._active_high:
            pin.value(1 if energise else 0)
        else:
            pin.value(0 if energise else 1)

    def on(self, zone_id):
        """Energise the relay for zone_id (opens the valve)."""
        pin = self._pins.get(zone_id)
        if pin:
            self._set_pin(pin, True)
            print("Relay ON: zone", zone_id)
        else:
            print("Relay: zone {} not configured/enabled — skipping".format(zone_id))

    def off(self, zone_id):
        """De-energise the relay for zone_id (closes the valve)."""
        pin = self._pins.get(zone_id)
        if pin:
            self._set_pin(pin, False)
            print("Relay OFF: zone", zone_id)

    def all_off(self):
        """
        De-energise ALL relay channels.
        MUST be the first hardware call on every boot.
        Also called on stop and in error handlers.
        """
        for zone_id, pin in self._pins.items():
            self._set_pin(pin, False)
        print("Relay: ALL zones OFF")

    def zone_ids(self):
        """Return list of configured (enabled) zone IDs."""
        return list(self._pins.keys())

    def is_zone_configured(self, zone_id):
        return zone_id in self._pins
