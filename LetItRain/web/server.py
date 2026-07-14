# web/server.py
# Lightweight HTTP JSON API server running on the Pico W.
#
# This server is the LOCAL control interface for the iOS app when
# it is on the same Wi-Fi network as the Pico. It exposes a minimal
# REST API — no HTML, no web UI.
#
# The HTML web interface has been removed. All control now goes
# through the iOS app (local mode) or Firebase (remote read-only).
#
# Endpoints:
#   GET  /status          → current device status as JSON
#   GET  /config          → current config as JSON
#   POST /start           → body: {"duration_minutes": N}  — manual start
#   POST /stop            → manual stop
#   POST /config          → body: full config dict — update and persist
#   POST /skip-today      → set local skip override for today's scheduled run
#   POST /cancel-skip     → clear local skip override
#
# The connect_wifi() function has been moved to network/wifi.py.
# Import it from there.

import ujson
import usocket


# ---------------------------------------------------------------------------
# JSON response helpers
# ---------------------------------------------------------------------------

def _json_response(conn, status_code, data_dict):
    """Send a JSON HTTP response and close the connection."""
    body = ujson.dumps(data_dict)
    status_line = {
        200: "200 OK",
        400: "400 Bad Request",
        405: "405 Method Not Allowed",
        500: "500 Internal Server Error",
    }.get(status_code, "{} Unknown".format(status_code))

    response = (
        "HTTP/1.1 {}\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: {}\r\n"
        "Access-Control-Allow-Origin: *\r\n"
        "Connection: close\r\n"
        "\r\n"
        "{}"
    ).format(status_line, len(body), body)

    try:
        conn.sendall(response.encode())
    finally:
        conn.close()


def _parse_request(raw):
    """
    Parse raw HTTP request bytes.
    Returns (method, path, body_dict | None).
    body_dict is None if there is no body or it cannot be parsed as JSON.
    """
    try:
        text   = raw.decode("utf-8", "ignore")
        lines  = text.split("\r\n")
        parts  = lines[0].split(" ")
        method = parts[0] if len(parts) > 0 else "GET"
        path   = parts[1].split("?")[0] if len(parts) > 1 else "/"

        # Extract body (after the blank line separating headers from body)
        body_dict = None
        if "\r\n\r\n" in text:
            body_str = text.split("\r\n\r\n", 1)[1].strip()
            if body_str:
                try:
                    body_dict = ujson.loads(body_str)
                except Exception:
                    pass

        return method, path, body_dict
    except Exception:
        return "GET", "/", None


# ---------------------------------------------------------------------------
# Main server function
# ---------------------------------------------------------------------------

def run_server(config, state, rtc, on_manual_start, on_manual_stop,
               sync_rtc_from_ntp, local_override, save_config_fn):
    """
    Run the HTTP JSON API server. This is designed to be called in a
    background thread via _thread.start_new_thread().

    Args:
        config:           config dict (mutable — changes are persisted)
        state:            ControllerState instance
        rtc:              DS3231 instance (may be None)
        on_manual_start:  callable() — triggers a manual run
        on_manual_stop:   callable() — stops the current run
        sync_rtc_from_ntp: callable() — sync RTC from NTP
        local_override:   mutable dict {"skip_today": bool, "skip_reason": str|None}
                          shared with main loop for local skip state
        save_config_fn:   callable(config) — persists config to flash
    """
    addr = usocket.getaddrinfo("0.0.0.0", 80)[0][-1]
    server = usocket.socket()
    server.setsockopt(usocket.SOL_SOCKET, usocket.SO_REUSEADDR, 1)
    server.bind(addr)
    server.listen(2)
    print("HTTP server listening on port 80")

    while True:
        try:
            conn, client_addr = server.accept()
            raw = conn.recv(2048)
            method, path, body = _parse_request(raw)
            print("HTTP {} {} from {}".format(method, path, client_addr))

            # ---------------------------------------------------------------
            # GET /status
            # ---------------------------------------------------------------
            if method == "GET" and path == "/status":
                last = config.get("last_run", {})
                s    = state
                data = {
                    "is_running":         s.is_running(),
                    "current_mode":       s.current_run_mode if s.is_running() else "idle",
                    "run_started_at":     s.current_run_start_epoch if s.is_running() else None,
                    "run_ends_at":        s.run_ends_at() if s.is_running() else None,
                    "last_run_start":     last.get("start_epoch"),
                    "last_run_end":       last.get("end_epoch"),
                    "last_run_mode":      last.get("mode"),
                    "last_run_status":    last.get("status"),
                    "active_skip":        local_override["skip_today"],
                    "active_skip_reason": local_override["skip_reason"],
                    "device_online":      True,
                }
                _json_response(conn, 200, data)

            # ---------------------------------------------------------------
            # GET /config
            # ---------------------------------------------------------------
            elif method == "GET" and path == "/config":
                _json_response(conn, 200, config)

            # ---------------------------------------------------------------
            # POST /start
            # ---------------------------------------------------------------
            elif method == "POST" and path == "/start":
                duration = config.get("manual_default_duration_minutes", 10)
                if body and "duration_minutes" in body:
                    try:
                        duration = int(body["duration_minutes"])
                    except (ValueError, TypeError):
                        pass
                on_manual_start(duration)
                _json_response(conn, 200, {"started": True, "duration_minutes": duration})

            # ---------------------------------------------------------------
            # POST /stop
            # ---------------------------------------------------------------
            elif method == "POST" and path == "/stop":
                on_manual_stop()
                _json_response(conn, 200, {"stopped": True})

            # ---------------------------------------------------------------
            # POST /config
            # ---------------------------------------------------------------
            elif method == "POST" and path == "/config":
                if body and isinstance(body, dict):
                    # Merge supplied keys into existing config
                    for k, v in body.items():
                        config[k] = v
                    save_config_fn(config)
                    _json_response(conn, 200, {"saved": True})
                else:
                    _json_response(conn, 400, {"error": "invalid JSON body"})

            # ---------------------------------------------------------------
            # POST /skip-today
            # ---------------------------------------------------------------
            elif method == "POST" and path == "/skip-today":
                local_override["skip_today"]  = True
                local_override["skip_reason"] = "manual_local"
                print("Local skip override SET")
                _json_response(conn, 200, {"skipped": True, "reason": "manual_local"})

            # ---------------------------------------------------------------
            # POST /cancel-skip
            # ---------------------------------------------------------------
            elif method == "POST" and path == "/cancel-skip":
                local_override["skip_today"]  = False
                local_override["skip_reason"] = None
                print("Local skip override CLEARED")
                _json_response(conn, 200, {"skipped": False})

            # ---------------------------------------------------------------
            # 404 / method not allowed
            # ---------------------------------------------------------------
            else:
                _json_response(conn, 405, {"error": "not found", "path": path})

        except OSError as ex:
            # Socket-level errors (client disconnected mid-request etc.)
            print("HTTP server socket error:", ex)
        except Exception as ex:
            print("HTTP server error:", ex)
            try:
                conn.close()
            except Exception:
                pass
