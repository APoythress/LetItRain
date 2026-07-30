# firebase/status_writer.py
# Writes device status and metadata to Firebase.
# Updated for multi-zone: includes active_zone_id in status.
#
# Ported to async (every write is now an await on FirebaseClient's httpx
# calls). free_mem_bytes/min_free_mem_bytes are dropped -- they tracked
# MicroPython's tiny fixed heap for OOM risk, which doesn't map to Linux's
# virtual memory model, and the iOS app never displayed them.

from core.unix_time import unix_time


class StatusWriter:

    def __init__(self, firebase_client, state, config, firmware_version, device_name):
        self._fb      = firebase_client
        self._state   = state
        self._config  = config
        self._version = firmware_version
        self._name    = device_name

    async def push_ip(self, local_ip):
        zones = self._config.get("zones", [])
        enabled_count = len([z for z in zones if z.get("enabled")])
        data = {
            "local_ip":         local_ip,
            "firmware_version": self._version,
            "device_name":      self._name,
            "zone_count":       enabled_count,
        }
        ok = await self._fb.patch("meta", data)
        if ok:
            print("Firebase: meta pushed (ip={})".format(local_ip))
        else:
            print("Firebase: meta push failed (non-fatal)")

    async def push_status(self, active_skip=False, active_skip_reason=None):
        s    = self._state
        last = self._config.get("last_run", {})
        data = {
            "is_running":         s.is_running(),
            "active_zone_id":     s.current_zone_id if s.is_running() else None,
            "current_mode":       s.current_run_mode if s.is_running() else "idle",
            "run_started_at":     s.current_run_start_epoch if s.is_running() else None,
            "run_ends_at":        s.run_ends_at() if s.is_running() else None,
            "last_run_start":     last.get("start_epoch"),
            "last_run_end":       last.get("end_epoch"),
            "last_run_mode":      last.get("mode"),
            "last_run_zone_id":   last.get("zone_id"),
            "last_run_status":    last.get("status"),
            "device_online":      True,
            "last_synced_epoch":  unix_time(),
            "active_skip":        active_skip,
            "active_skip_reason": active_skip_reason,
            "firmware_version":   self._version,
        }
        if not await self._fb.patch("status", data):
            print("Firebase: status push failed (non-fatal)")

    async def push_last_run(self, start_epoch, end_epoch, mode, zone_id, status_str):
        data = {
            "last_run_start":    start_epoch,
            "last_run_end":      end_epoch,
            "last_run_mode":     mode,
            "last_run_zone_id":  zone_id,
            "last_run_status":   status_str,
            "is_running":        False,
            "active_zone_id":    None,
            "current_mode":      "idle",
            "run_started_at":    None,
            "run_ends_at":       None,
            "last_synced_epoch": unix_time(),
        }
        if not await self._fb.patch("status", data):
            print("Firebase: push_last_run failed (non-fatal)")

    async def push_offline(self):
        await self._fb.patch("status", {
            "device_online":     False,
            "last_synced_epoch": unix_time(),
        })
        print("Firebase: device marked offline")
