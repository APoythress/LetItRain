# firebase/override_reader.py
# Reads the overrides node from Firebase to determine if today's
# scheduled run should be skipped.
#
# Called only when the scheduler is about to fire a run — not on
# every main loop iteration — to minimise Firebase reads.
#
# FAIL-OPEN DESIGN:
#   If the Firebase read fails for any reason (network error, timeout,
#   bad token) this module returns (False, None) so the scheduled run
#   proceeds normally. A network failure must never block watering.
#
# FUTURE (v1.2) — rain threshold:
#   When the IFTTT rain hook is implemented, rain_inches will be
#   populated in the overrides node. The check will be:
#     skip if rain_inches >= config["rain_skip_threshold_inches"]
#   The slot for this logic is marked below with a FUTURE comment.


class OverrideReader:
    """
    Reads and interprets the Firebase overrides node.
    """

    def __init__(self, firebase_client):
        """
        Args:
            firebase_client: FirebaseClient instance
        """
        self._fb = firebase_client

    def get_active_skip(self, today_date_string):
        """
        Check whether today's scheduled run should be skipped.

        Args:
            today_date_string: Today's date as "YYYY-MM-DD" string (from RTC).

        Returns:
            (skip_active: bool, skip_reason: str | None)

            skip_active  — True if the run should be skipped
            skip_reason  — "manual_remote" | "rain" | "manual_local" | None
        """
        try:
            data = self._fb.get("overrides")
        except Exception as ex:
            print("OverrideReader: get exception:", ex)
            return False, None  # fail open

        if data is None:
            # Firebase read failed or node doesn't exist yet
            return False, None

        skip_today = data.get("skip_today", False)
        if not skip_today:
            return False, None

        skip_date = data.get("skip_date")
        if skip_date != today_date_string:
            # Skip was set for a different date — treat as expired
            return False, None

        skip_reason = data.get("skip_reason", "unknown")

        # ----------------------------------------------------------------
        # FUTURE v1.2 — Rain threshold logic slot
        # ----------------------------------------------------------------
        # rain_inches = data.get("rain_inches")
        # if skip_reason == "rain" and rain_inches is not None:
        #     threshold = config.get("rain_skip_threshold_inches", 0.1)
        #     if float(rain_inches) < threshold:
        #         print("OverrideReader: rain_inches {} below threshold {}; not skipping".format(
        #             rain_inches, threshold))
        #         return False, None
        # ----------------------------------------------------------------

        print("OverrideReader: skip active — reason:", skip_reason)
        return True, skip_reason
