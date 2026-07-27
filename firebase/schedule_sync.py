# firebase/schedule_sync.py
# Pushes the Pico's local schedule/zone config to Firebase as a read-only
# mirror for the app's remote view (zone names in the last-run summary,
# the "a schedule exists" check for the skip card).
#
# Push-only, deliberately: schedule editing is local-only now (writes go
# straight to the Pico's own /config over the LAN, and the security rules
# reject a zones/schedule write from the app entirely -- see root README).
# An earlier version of this module also pulled Firebase's copy back into
# local config on a timer, which meant a schedule edited locally could be
# silently overwritten by a stale Firebase copy up to an hour later, since
# nothing pushed the local edit up in between. Don't reintroduce a pull
# without also reintroducing a way for local edits to reach Firebase first.


class ScheduleSync:
    """
    Pushes the local zone/schedule config to Firebase.
    """

    def __init__(self, firebase_client, config):
        self._fb     = firebase_client
        self._config = config

    def push(self):
        """
        Push current local zones + schedule to Firebase. Call at boot and
        during the periodic cloud-sync pass. Cheap enough to run
        unconditionally rather than diffing first -- it's two requests,
        once an hour.
        """
        self._push_zones_to_firebase()
        self._push_schedule_to_firebase()

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
