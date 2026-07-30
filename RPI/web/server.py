# web/server.py
# Local HTTP JSON API. Multi-zone aware.
#
# Ported from a hand-rolled usocket server (a memory/dependency constraint
# on the Pico) to FastAPI, running inside the same asyncio event loop as
# the rest of the app via uvicorn's ASGI server (see main.py). Endpoint
# paths and response JSON shapes are unchanged so the existing iOS app
# needs no changes -- except free_mem_bytes/min_free_mem_bytes/
# heap_total_bytes, dropped from /status (see core/mem_diag's removal:
# unused by the app, doesn't map to Linux's memory model) and
# /check-update, omitted because OTA is out of scope for this alpha
# (see update/updater.py).
#
# Endpoints:
#   GET  /status          → current run status (zone-aware)
#   GET  /config          → full config including zones and schedule
#   POST /start           → {"zone_id": 1, "duration_minutes": 10}
#   POST /stop             → stop current zone
#   POST /config          → replace config (zones + schedule)
#   POST /skip-today      → set local skip override
#   POST /cancel-skip     → clear local skip override
#   POST /resync-time     → trigger an immediate DS3231 resync from the
#                           system clock (also runs automatically on its
#                           own periodic cadence -- see main.py)
#   GET  /boot-log        → last boot's diagnostics (Wi-Fi/Firebase/RTC
#                           status) -- see main.py's boot_log.json write

import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


async def _body_or_none(request: Request):
    """Best-effort JSON body parse -- None for an empty body or anything
    that doesn't parse, mirroring the old hand-rolled parser's forgiving
    behavior so callers can fall back to defaults instead of erroring."""
    raw = await request.body()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def create_app(config, state, rtc, on_manual_start, on_manual_stop,
                on_zones_changed, local_override, local_resync_trigger,
                save_config_fn, now_fn, firmware_version):
    """
    Build the FastAPI app. All the shared, already-initialized objects
    (config dict, ControllerState, DS3231 or None, the boot-time
    callbacks/triggers) are closed over by the route handlers below,
    the same shared-state shape the old run_server(...) parameters used.
    """
    app = FastAPI()

    @app.get("/status")
    async def get_status():
        last = config.get("last_run", {})
        s = state
        return {
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
            "active_skip":        local_override["skip_today"],
            "active_skip_reason": local_override["skip_reason"],
            "device_online":      True,
            "last_synced_epoch":  now_fn(),
            "firmware_version":   firmware_version,
        }

    @app.get("/config")
    async def get_config():
        return config

    @app.post("/start")
    async def start(request: Request):
        body = await _body_or_none(request)
        zone_id  = int(body.get("zone_id", 1)) if body else 1
        duration = int(body.get("duration_minutes",
                       config.get("manual_default_duration_minutes", 10))) if body else 10
        started = await on_manual_start(zone_id, duration)
        if not started:
            return JSONResponse(status_code=409, content={
                "started": False,
                "zone_id": zone_id,
                "error": "zone not configured/enabled",
            })
        return {"started": True, "zone_id": zone_id, "duration_minutes": duration}

    @app.post("/stop")
    async def stop():
        await on_manual_stop()
        return {"stopped": True}

    @app.post("/config")
    async def post_config(request: Request):
        body = await _body_or_none(request)
        if body and isinstance(body, dict):
            for k, v in body.items():
                config[k] = v
            save_config_fn(config)
            if "zones" in body:
                on_zones_changed(config.get("zones", []))
            return {"saved": True}
        return JSONResponse(status_code=400, content={"error": "invalid JSON body"})

    @app.post("/skip-today")
    async def skip_today():
        local_override["skip_today"]  = True
        local_override["skip_reason"] = "manual_local"
        return {"skipped": True, "reason": "manual_local"}

    @app.post("/cancel-skip")
    async def cancel_skip():
        local_override["skip_today"]  = False
        local_override["skip_reason"] = None
        return {"skipped": False}

    @app.post("/resync-time")
    async def resync_time():
        local_resync_trigger["requested"] = True
        return {"requested": True}

    @app.get("/boot-log")
    async def boot_log():
        try:
            with open("boot_log.json", "r") as f:
                return json.load(f)
        except Exception:
            # Missing on a device that hasn't rebooted since this feature
            # was added, or a corrupt/partial write -- either way, a clear
            # response beats a generic 500.
            return JSONResponse(status_code=404, content={"error": "no boot log available yet"})

    return app
