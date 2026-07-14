# firebase/status_writer.py
# Handles all Pico-to-Firebase writes.
# The Pico only ever WRITES to Firebase (except for reading overrides).
# Status is pushed every 15 seconds as a heartbeat.

import utime


class StatusWriter:
    """
    Writes device status, metadata, and last-run info to Firebase.

    All writes are best-effort: if a push fails the scheduler loop
    continues normally. The next heartbeat will catch up.
    """

    def __init__(self, firebase_client, state, config, firmware_version, device_name):
        """
        Args:
            firebase_client:  FirebaseClient instance
            state:            ControllerState instance
            config:           config dict (loaded from config.json)
            firmware_version: string e.g. "1.1.0"
            device_name:      string from config["device_name"]
        """
        self._fb      = firebase_client
        self._state   = state
        self._config  = config
        self._version = firmware_version
        self._name    = device_name

    def push_ip(self, local_ip):
        """
        Write the Pico's local IP and firmware info to Firebase.
        Called once at boot after Wi-Fi connects so the iOS app
        knows which IP to probe for local mode.

        Args:
            local_ip: string e.g. "192.168.1.42"
        """
        data = {
            "local_ip":        local_ip,
            "firmware_version": self._version,
            "device_name":     self._name,
        }
        ok = self._fb.patch("meta", data)
        if ok:
            print("Firebase: meta/local_ip pushed:", local_ip)
        else:
            print("Firebase: failed to push meta/local_ip (non-fatal)")

    def push_status(self, active_skip=False, active_skip_reason=None):
        """
        Push current device status to Firebase.
        Called every 15 seconds from the main loop.

        Args:
            active_skip:        bool — True if today's scheduled run is skipped
            active_skip_reason: string | None — "manual_remote" | "rain" | "manual_local"
        """
        s = self._state
        last = self._config.get("last_run", {})

        data = {
            "is_running":          s.is_running(),
            "current_mode":        s.current_run_mode if s.is_running() else "idle",
            "run_started_at":      s.current_run_start_epoch if s.is_running() else None,
            "run_ends_at":         s.run_ends_at() if s.is_running() else None,
            "last_run_start":      last.get("start_epoch"),
            "last_run_end":        last.get("end_epoch"),
            "last_run_mode":       last.get("mode"),
            "last_run_status":     last.get("status"),
            "device_online":       True,
            "last_heartbeat":      utime.time(),
            "active_skip":         active_skip,
            "active_skip_reason":  active_skip_reason,
            "firmware_version":    self._version,
        }

        ok = self._fb.patch("status", data)
        if not ok:
            print("Firebase: status push failed (non-fatal)")

    def push_last_run(self, start_epoch, end_epoch, mode, status_str):
        """
        Immediately push last-run details after a run ends.
        This ensures the app sees the result without waiting 15s
        for the next full heartbeat.

        Args:
            start_epoch: Unix epoch when run started
            end_epoch:   Unix epoch when run ended
            mode:        "manual" | "scheduled"
            status_str:  "completed" | "manual_stop" | "skipped"
        """
        data = {
            "last_run_start":  start_epoch,
            "last_run_end":    end_epoch,
            "last_run_mode":   mode,
            "last_run_status": status_str,
            "is_running":      False,
            "current_mode":    "idle",
            "run_started_at":  None,
            "run_ends_at":     None,
            "last_heartbeat":  utime.time(),
        }
        ok = self._fb.patch("status", data)
        if not ok:
            print("Firebase: push_last_run failed (non-fatal)")

    def push_offline(self):
        """
        Mark device as offline in Firebase.
        Called in a try/finally in main() on clean shutdown.
        Note: cannot be guaranteed on hard power loss — that is acceptable.
        """
        self._fb.patch("status", {
            "device_online":  False,
            "last_heartbeat": utime.time(),
        })
        print("Firebase: device marked offline")
