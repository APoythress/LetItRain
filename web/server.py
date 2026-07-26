# web/server.py
# Local HTTP JSON API. Multi-zone aware.
#
# Endpoints:
#   GET  /status          → current run status (zone-aware)
#   GET  /config          → full config including zones and schedule
#   POST /start           → {"zone_id": 1, "duration_minutes": 10}
#   POST /stop            → stop current zone
#   POST /config          → replace config (zones + schedule)
#   POST /skip-today      → set local skip override
#   POST /cancel-skip     → clear local skip override
#   POST /check-update    → trigger an immediate OTA check (bypasses the
#                           hourly cloud-sync pass main.py otherwise waits for)

import ujson
import usocket
import gc

from core import mem_diag


def _json_response(conn, status_code, data_dict):
    body = ujson.dumps(data_dict)
    status_line = {200: "200 OK", 400: "400 Bad Request",
                   405: "405 Method Not Allowed", 500: "500 Internal Server Error"
                   }.get(status_code, "{} Unknown".format(status_code))
    header = (
        "HTTP/1.1 {}\r\nContent-Type: application/json\r\n"
        "Content-Length: {}\r\nAccess-Control-Allow-Origin: *\r\n"
        "Connection: close\r\n\r\n"
    ).format(status_line, len(body))
    try:
        # Sent as two pieces rather than one combined+encoded string: for a
        # response like /config or /logs, concatenating header+body into one
        # string and then encoding it means 3 full-size copies of roughly the
        # same data alive at once (json string, combined string, encoded
        # bytes) at exactly the moment memory is already tightest.
        conn.sendall(header.encode())
        conn.sendall(body.encode())
    finally:
        conn.close()
    mem_diag.sample()
    gc.collect()


def _read_request(conn, max_bytes=16384):
    """
    Read a full HTTP request, looping recv() until the header block AND the
    full Content-Length body have arrived.

    A single recv() call can return only the headers if the client sends
    headers and body as separate TCP writes (common for POST requests over
    Wi-Fi) -- this was silently truncating request bodies (e.g. a manual
    start's duration_minutes), leaving _parse_request() with an empty body
    and falling back to defaults with no visible error.

    Chunks are collected in a list and joined once at the end rather than
    repeated `data += chunk`, which reallocates and copies the entire
    buffer-so-far on every append (O(n^2) for a multi-chunk body, and each
    intermediate copy is immediately garbage). max_bytes dropped from a
    generic 64KB to 16KB -- every real local payload (JSON commands, the
    full schedule) is a few KB at most, so this just caps the worst case
    tighter without touching any legitimate request.
    """
    conn.settimeout(5)
    chunks = []
    total = 0
    header_end = -1
    header_bytes = b""

    while header_end == -1:
        chunk = conn.recv(1024)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        total += len(chunk)
        header_bytes = b"".join(chunks)
        header_end = header_bytes.find(b"\r\n\r\n")
        if total > max_bytes:
            return header_bytes

    header_text = header_bytes[:header_end].decode("utf-8", "ignore")
    content_length = 0
    for line in header_text.split("\r\n"):
        if line.lower().startswith("content-length:"):
            try:
                content_length = int(line.split(":", 1)[1].strip())
            except ValueError:
                content_length = 0
            break

    body_so_far = total - (header_end + 4)
    while body_so_far < content_length and total < max_bytes:
        chunk = conn.recv(1024)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        body_so_far += len(chunk)

    return b"".join(chunks)


def _parse_request(raw):
    try:
        text   = raw.decode("utf-8", "ignore")
        lines  = text.split("\r\n")
        parts  = lines[0].split(" ")
        method = parts[0] if len(parts) > 0 else "GET"
        path   = parts[1].split("?")[0] if len(parts) > 1 else "/"
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


def run_server(config, state, rtc, on_manual_start, on_manual_stop,
               local_override, local_update_trigger, save_config_fn, now_fn,
               firmware_version):
    addr = usocket.getaddrinfo("0.0.0.0", 80)[0][-1]
    server = usocket.socket()
    server.setsockopt(usocket.SOL_SOCKET, usocket.SO_REUSEADDR, 1)
    server.bind(addr)
    server.listen(5)  # a manual start/stop triggers an immediate extra poll on
                       # top of the regular 3s timer, so short bursts of 3-4
                       # near-simultaneous local requests are normal
    print("HTTP server listening on port 80")

    while True:
        conn = None
        try:
            conn, client_addr = server.accept()
            raw = _read_request(conn)
            method, path, body = _parse_request(raw)
            # /status is polled every few seconds by design (app poll +
            # connection probe) -- logging every hit just crowds out the
            # actually-interesting lines (commands, errors) in the capped
            # /logs buffer. Everything else still logs normally.
            if path != "/status":
                print("HTTP {} {} from {}".format(method, path, client_addr))

            if method == "GET" and path == "/status":
                last = config.get("last_run", {})
                s    = state
                _json_response(conn, 200, {
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
                    "free_mem_bytes":     gc.mem_free(),
                    "min_free_mem_bytes": mem_diag.min_free(),
                    "heap_total_bytes":   mem_diag.heap_total(),
                })

            elif method == "GET" and path == "/config":
                _json_response(conn, 200, config)

            elif method == "POST" and path == "/start":
                zone_id  = int(body.get("zone_id",  1)) if body else 1
                duration = int(body.get("duration_minutes",
                               config.get("manual_default_duration_minutes", 10))) if body else 10
                on_manual_start(zone_id, duration)
                _json_response(conn, 200, {"started": True,
                                           "zone_id": zone_id,
                                           "duration_minutes": duration})

            elif method == "POST" and path == "/stop":
                on_manual_stop()
                _json_response(conn, 200, {"stopped": True})

            elif method == "POST" and path == "/config":
                if body and isinstance(body, dict):
                    for k, v in body.items():
                        config[k] = v
                    save_config_fn(config)
                    _json_response(conn, 200, {"saved": True})
                else:
                    _json_response(conn, 400, {"error": "invalid JSON body"})

            elif method == "POST" and path == "/skip-today":
                local_override["skip_today"]  = True
                local_override["skip_reason"] = "manual_local"
                _json_response(conn, 200, {"skipped": True, "reason": "manual_local"})

            elif method == "POST" and path == "/cancel-skip":
                local_override["skip_today"]  = False
                local_override["skip_reason"] = None
                _json_response(conn, 200, {"skipped": False})

            elif method == "POST" and path == "/check-update":
                local_update_trigger["requested"] = True
                _json_response(conn, 200, {"requested": True})

            else:
                _json_response(conn, 405, {"error": "not found", "path": path})

        except Exception as ex:
            # Covers OSError (timeout/reset from _read_request's settimeout,
            # a dropped connection mid-request, etc.) as well as anything
            # else -- every path here MUST close conn, or a leaked socket
            # on this board's very small lwIP pool eventually starves both
            # this server and the outbound Firebase/OTA calls on the main
            # loop thread that share the same pool.
            print("HTTP server error:", ex)
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
