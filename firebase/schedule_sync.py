# firebase/schedule_sync.py
# Reads schedule and zone config from Firebase Realtime Database
# and merges into the local config dict.
#
# The Pico now reads schedule FROM Firebase so changes made in the iOS
# app (remote mode) reach the Pico without a local connection.
# Local config.json is updated on every successful sync so the schedule
# survives a reboot without Firebase.

import ujson


# Days in MicroPython weekday order (0=Mon)
DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday",
             "friday", "saturday", "sunday"]


class ScheduleSync:
    """
    Pulls schedule and zone config from Firebase into the local config dict.
    """

    def __init__(self, firebase_client, config, save_config_fn):
        self._fb          = firebase_client
        self._config      = config
        self._save_config = save_config_fn

    def push_initial(self):
        """
        On first boot, if Firebase schedule node is null/empty, push the
        local config up so the app has something to display immediately.
        """
        existing = self._fb.get("schedule")
        if existing is None or existing == "null":
            self._push_schedule_to_firebase()

        existing_zones = self._fb.get("zones")
        if existing_zones is None or existing_zones == "null":
            self._push_zones_to_firebase()

    def sync(self):
        """
        Pull schedule and zones from Firebase into local config.
        Called once at boot and every 60 seconds in the main loop.
        Returns True if anything changed.
        """
        changed = False

        # --- Zones ---
        zones_data = self._fb.get("zones")
        if isinstance(zones_data, dict):
            # Firebase stores as {"1": {...}, "2": {...}} keyed by zone id string
            merged_zones = []
            for k, v in zones_data.items():
                if isinstance(v, dict):
                    zone = {
                        "id":      int(k),
                        "name":    v.get("name", "Zone {}".format(k)),
                        "pin":     v.get("pin", 0),
                        "enabled": v.get("enabled", False),
                    }
                    merged_zones.append(zone)
            if merged_zones:
                merged_zones.sort(key=lambda z: z["id"])
                self._config["zones"] = merged_zones
                self._config["zone_count"] = len([z for z in merged_zones if z["enabled"]])
                changed = True

        # --- Schedule ---
        schedule_data = self._fb.get("schedule")
        if isinstance(schedule_data, dict):
            merged_schedule = {}
            for day in DAY_NAMES:
                day_data = schedule_data.get(day, {})
                if isinstance(day_data, dict):
                    raw_slots = day_data.get("slots", {})
                    # Firebase returns list or dict; normalise to list
                    if isinstance(raw_slots, dict):
                        slots = [raw_slots[k] for k in sorted(raw_slots.keys(),
                                 key=lambda x: int(x) if x.isdigit() else 0)]
                    elif isinstance(raw_slots, list):
                        slots = raw_slots
                    else:
                        slots = []

                    # Validate each slot has required keys
                    valid_slots = []
                    for s in slots:
                        if isinstance(s, dict) and all(
                            k in s for k in ("zone", "start_hour", "start_minute", "duration_minutes")
                        ):
                            valid_slots.append(s)

                    merged_schedule[day] = {
                        "enabled": day_data.get("enabled", False),
                        "slots":   valid_slots,
                    }
                else:
                    merged_schedule[day] = {"enabled": False, "slots": []}

            self._config["schedule"] = merged_schedule
            changed = True

        if changed:
            self._save_config(self._config)
            print("ScheduleSync: config updated from Firebase")

        return changed

    def _push_schedule_to_firebase(self):
        schedule = self._config.get("schedule", {})
        # Convert slots lists to dicts for Firebase (Firebase prefers indexed children)
        fb_schedule = {}
        for day, day_data in schedule.items():
            slots = day_data.get("slots", [])
            fb_schedule[day] = {
                "enabled": day_data.get("enabled", False),
                "slots":   {str(i): s for i, s in enumerate(slots)},
            }
        self._fb.patch("schedule", fb_schedule)
        print("ScheduleSync: pushed local schedule to Firebase")

    def _push_zones_to_firebase(self):
        zones = self._config.get("zones", [])
        fb_zones = {str(z["id"]): {
            "name":    z.get("name", "Zone {}".format(z["id"])),
            "pin":     z.get("pin", 0),
            "enabled": z.get("enabled", False),
        } for z in zones}
        self._fb.patch("zones", fb_zones)
        print("ScheduleSync: pushed local zones to Firebase")
