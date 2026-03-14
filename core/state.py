class ControllerState:
    def __init__(self):
        self.status = "off"
        self.current_run_start_epoch = None
        self.current_run_duration_seconds = 0
        self.current_run_mode = None
        self.last_action = "boot"

    def start_run(self, start_epoch, duration_seconds, mode):
        self.status = "running"
        self.current_run_start_epoch = start_epoch
        self.current_run_duration_seconds = duration_seconds
        self.current_run_mode = mode
        self.last_action = "started_" + mode

    def stop_run(self):
        self.status = "off"
        self.current_run_start_epoch = None
        self.current_run_duration_seconds = 0
        self.current_run_mode = None
        self.last_action = "stopped"

    def is_running(self):
        return self.status == "running"

    def run_end_epoch(self):
        if self.current_run_start_epoch is None:
            return None
        return self.current_run_start_epoch + self.current_run_duration_seconds
