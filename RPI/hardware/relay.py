# hardware/relay.py
# Multi-zone relay controller.
#
# Manages up to 5 relay channels, one per zone.
# Each zone maps to a GPIO pin defined in config["zones"].
#
# Relay boards are typically ACTIVE LOW (relay energises when pin is LOW).
# Set active_high=False if your board energises on LOW (most common for
# mechanical relay hat boards). Set True for solid-state relays.
#
# gpiozero's OutputDevice takes active_high natively -- .on()/.off() always
# mean "energised"/"de-energised" regardless of polarity, so this no longer
# needs its own _set_pin() polarity translation like the machine.Pin version did.

from gpiozero import OutputDevice


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
        self._devices = {}   # zone_id (int) → OutputDevice
        self._build_devices(zones_config)

    def _build_devices(self, zones_config):
        for zone in zones_config:
            zone_id = zone.get("id")
            pin_num = zone.get("pin")
            enabled = zone.get("enabled", False)
            if zone_id and pin_num is not None and enabled:
                device = OutputDevice(pin_num, active_high=self._active_high, initial_value=False)
                self._devices[zone_id] = device
                print("Relay: zone {} -> GPIO{}".format(zone_id, pin_num))

    def reconfigure(self, zones_config):
        """
        Rebuild the pin map from an updated zones config (e.g. after a
        /config POST changes which zones are enabled or which pins they
        use). Safe to call while idle or mid-run -- every existing device
        is de-energised before being released, so a zone that becomes
        disabled or gets reassigned to a different pin can't stay
        energised on its old pin.
        """
        for device in self._devices.values():
            device.off()
            device.close()
        self._devices = {}
        self._build_devices(zones_config)

    def on(self, zone_id):
        """Energise the relay for zone_id (opens the valve)."""
        device = self._devices.get(zone_id)
        if device:
            device.on()
            print("Relay ON: zone", zone_id)
        else:
            print("Relay: zone {} not configured/enabled - skipping".format(zone_id))

    def off(self, zone_id):
        """De-energise the relay for zone_id (closes the valve)."""
        device = self._devices.get(zone_id)
        if device:
            device.off()
            print("Relay OFF: zone", zone_id)

    def all_off(self):
        """
        De-energise ALL relay channels.
        MUST be the first hardware call on every boot.
        Also called on stop and in error handlers.
        """
        for device in self._devices.values():
            device.off()
        print("Relay: ALL zones OFF")

    def zone_ids(self):
        """Return list of configured (enabled) zone IDs."""
        return list(self._devices.keys())

    def is_zone_configured(self, zone_id):
        return zone_id in self._devices
