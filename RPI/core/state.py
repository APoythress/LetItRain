# core/state.py
# Controller state — tracks what is running right now.
# Extended for multi-zone: tracks which zone is active.


class ControllerState:
    """
    In-memory representation of the controller's current run state.
    Shared between the main loop and the HTTP server thread.
    All properties are plain Python — no locking needed for reads/writes
    of scalar types on MicroPython.
    """

    def __init__(self):
        self._running            = False
        self.current_run_mode    = None   # "manual" | "scheduled"
        self.current_zone_id     = None   # int 1-5
        self.current_run_start_epoch = None
        self._run_duration_seconds   = None

    # ------------------------------------------------------------------
    # Run control
    # ------------------------------------------------------------------

    def start_run(self, epoch, duration_seconds, mode, zone_id):
        self._running                = True
        self.current_run_mode        = mode
        self.current_zone_id         = zone_id
        self.current_run_start_epoch = epoch
        self._run_duration_seconds   = duration_seconds

    def stop_run(self):
        self._running                = False
        self.current_run_mode        = None
        self.current_zone_id         = None
        self.current_run_start_epoch = None
        self._run_duration_seconds   = None

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def is_running(self):
        return self._running

    def run_ends_at(self):
        """Return the epoch when the current run is expected to end, or None."""
        if not self._running or self.current_run_start_epoch is None:
            return None
        return self.current_run_start_epoch + self._run_duration_seconds

    def should_stop_now(self, now_epoch):
        """True if a run is active and the scheduled end time has passed."""
        ends_at = self.run_ends_at()
        if ends_at is None:
            return False
        return now_epoch >= ends_at
