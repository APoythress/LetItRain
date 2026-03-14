import socket
import network
import utime
from core.scheduler import next_run_epoch
from web.html import render_dashboard
from storage.config_store import save_config
from update.updater import check_for_update

def connect_wifi(ssid, password, timeout_seconds=20):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        return wlan

    wlan.connect(ssid, password)
    start = utime.time()

    while not wlan.isconnected():
        if utime.time() - start > timeout_seconds:
            raise RuntimeError("Wi-Fi connection timed out")
        utime.sleep(1)

    return wlan

def parse_query(path):
    if "?" not in path:
        return path, {}

    route, query = path.split("?", 1)
    params = {}

    for pair in query.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)

            # basic decode for this project
            v = v.replace("%3A", ":").replace("%2C", ",").replace("+", " ")

            if k in params:
                if isinstance(params[k], list):
                    params[k].append(v)
                else:
                    params[k] = [params[k], v]
            else:
                params[k] = v

    return route, params


def http_response(body, content_type="text/html"):
    return "HTTP/1.1 200 OK\r\nContent-Type: {}\r\nConnection: close\r\n\r\n{}".format(content_type, body)

def redirect(location="/"):
    return "HTTP/1.1 302 Found\r\nLocation: {}\r\nConnection: close\r\n\r\n".format(location)

def run_server(config, state, rtc, on_manual_start, on_manual_stop, on_sync_rtc):
    addr = socket.getaddrinfo("0.0.0.0", 8080)[0][-1]
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(addr)
    server.listen(5)
    print("Web server listening on", addr)
    print("Server: ", server)
    while True:
        client, _ = server.accept()
        try:
            client.settimeout(2)
            raw = client.recv(1024)

            if not raw:
                client.close()
                continue

            request = raw.decode("utf-8")
            request_line = request.split("\r\n")[0]
            method, path, _proto = request_line.split(" ", 2)
            route, params = parse_query(path)

            print(request)

            if route == "/favicon.ico":
                client.send(b"HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n")
            
            # Manual update trigger
            elif route == "/update":
                client.send(http_response(
                    "<html><body><h1>Update Started</h1><p>Check the dashboard again in a few seconds.</p></body></html>"
                ).encode())

                client.close()
                client = None

                try:
                    check_for_update()
                except Exception as ex:
                    print("Update failed:", ex)
                continue

            # Manually sync rtc
            elif route == "/sync-rtc":
                try:
                    new_time = on_sync_rtc()
                    client.send(http_response(
                        "<html><body><h1>RTC Synced</h1><p>New RTC time: {}</p><p><a href='/'>Back</a></p></body></html>".format(new_time)
                    ).encode())
                except Exception as ex:
                    client.send(http_response(
                        "<html><body><h1>RTC Sync Error</h1><pre>{}</pre><p><a href='/'>Back</a></p></body></html>".format(str(ex))
                    ).encode())


            # Manual start
            elif route == "/start":
                on_manual_start()
                client.send(redirect().encode())

            # Manual stop
            elif route == "/stop":
                on_manual_stop()
                client.send(redirect().encode())

            # Manual save 
            elif route == "/save":
                try:
                    schedule = config["schedule"]

                    enabled_raw = str(params.get("enabled", "0")).strip()
                    appt_raw = str(params.get("appt", "06:00")).strip()
                    duration_raw = str(params.get("duration", str(schedule.get("duration_minutes", 10)))).strip()

                    days_raw = params.get("days", [])
                    if not isinstance(days_raw, list):
                        days_raw = [days_raw]

                    print("SAVE PARAMS:")
                    print("enabled =", enabled_raw)
                    print("days    =", days_raw)
                    print("appt    =", appt_raw)
                    print("duration=", duration_raw)

                    schedule["enabled"] = enabled_raw == "1"

                    day_list = []
                    for x in days_raw:
                        x = str(x).strip()
                        if x != "":
                            day_list.append(int(x))
                    schedule["days"] = sorted(day_list)

                    if ":" not in appt_raw:
                        raise ValueError("Time must be in HH:MM format")

                    hour_str, minute_str = appt_raw.split(":", 1)
                    schedule["start_hour"] = int(hour_str)
                    schedule["start_minute"] = int(minute_str)
                    schedule["duration_minutes"] = int(duration_raw)

                    print("NEW SCHEDULE =", schedule)

                    save_config(config)
                    client.send(redirect().encode())

                except Exception as ex:
                    print("SAVE ERROR:", ex)
                    client.send(http_response(
                        "<h1>Save Error</h1><pre>{}</pre><p><a href='/'>Back</a></p>".format(str(ex))
                    ).encode())


            # Dashboard
            else:
                now_epoch = rtc.epoch()
                now_iso = rtc.iso_string()


                body = render_dashboard(
                    config=config,
                    state=state,
                    now_iso=now_iso,
                    next_run_epoch=next_run_epoch(config.get("schedule", {}), now_epoch),
                )
                response = http_response(body).encode()
                client.send(response)
                utime.sleep_ms(50)

        except Exception as ex:
            print("Server error:", ex)
            try:
                if client is not None:
                    client.send(http_response(
                        "<h1>Error</h1><pre>{}</pre>".format(str(ex))
                    ).encode())
            except Exception as send_ex:
                print("Could not send error response:", send_ex)

        
        finally:
            try:
                client.close()
            except:
                pass
