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
            params[k] = v
    return route, params

def http_response(body, content_type="text/html"):
    return "HTTP/1.1 200 OK\r\nContent-Type: {}\r\nConnection: close\r\n\r\n{}".format(content_type, body)

def redirect(location="/"):
    return "HTTP/1.1 302 Found\r\nLocation: {}\r\nConnection: close\r\n\r\n".format(location)

def run_server(config, state, rtc, on_manual_start, on_manual_stop):
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
                check_for_update()
                continue


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
                schedule = config["schedule"]
                schedule["enabled"] = params.get("enabled", "0") == "1"
                days_csv = params.get("days", "")
                schedule["days"] = [int(x) for x in days_csv.split(",") if x.strip() != ""]
                schedule["start_hour"] = int(params.get("hour", schedule.get("start_hour", 6)))
                schedule["start_minute"] = int(params.get("minute", schedule.get("start_minute", 0)))
                schedule["duration_minutes"] = int(params.get("duration", schedule.get("duration_minutes", 10)))
                save_config(config)
                client.send(redirect().encode())

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
            client.send(http_response("<h1>Error</h1><pre>{}</pre>".format(str(ex))).encode())
        
        finally:
            try:
                client.close()
            except:
                pass
