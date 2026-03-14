import socket
import machine
import ujson
import utime
import os

VERSION_URL = "http://raw.githubusercontent.com/APoythress/LetItRain/main/version.json"
LOCAL_VERSION_FILE = "version.json"
UPDATE_STATUS_FILE = "update_status.json"


def set_update_status(status, message):
    data = {
        "status": status,
        "message": message,
        "updated_at": utime.time()
    }
    with open(UPDATE_STATUS_FILE, "w") as f:
        ujson.dump(data, f)


def get_update_status():
    try:
        with open(UPDATE_STATUS_FILE, "r") as f:
            return ujson.load(f)
    except:
        return {
            "status": "unknown",
            "message": "No update status file found."
        }


def get_local_version():
    try:
        with open(LOCAL_VERSION_FILE, "r") as f:
            data = ujson.load(f)
            return data.get("version", "0.0.0")
    except:
        return "0.0.0"


def save_local_version(version):
    with open(LOCAL_VERSION_FILE, "w") as f:
        ujson.dump({"version": version}, f)


def parse_version(version):
    return [int(x) for x in version.split(".")]


def is_newer(remote_version, local_version):
    return parse_version(remote_version) > parse_version(local_version)


def parse_url(url):
    if not url.startswith("http://"):
        raise ValueError("For now, use http:// URLs only.")

    url = url[7:]
    parts = url.split("/", 1)
    host = parts[0]
    path = "/" + parts[1] if len(parts) > 1 else "/"
    return host, path


def http_get(url):
    host, path = parse_url(url)

    addr = socket.getaddrinfo(host, 80)[0][-1]
    s = socket.socket()
    s.connect(addr)

    req = (
        "GET {} HTTP/1.1\r\n"
        "Host: {}\r\n"
        "Connection: close\r\n\r\n"
    ).format(path, host)

    s.send(req.encode())

    response = b""
    while True:
        chunk = s.recv(1024)
        if not chunk:
            break
        response += chunk

    s.close()

    parts = response.split(b"\r\n\r\n", 1)
    if len(parts) != 2:
        raise RuntimeError("Invalid HTTP response")

    headers, body = parts
    return body


def ensure_parent_folders(path):
    parts = path.split("/")
    current = ""
    for part in parts[:-1]:
        if not part:
            continue
        current = current + "/" + part if current else part
        try:
            os.mkdir(current)
        except OSError:
            pass


def download_file(file_info):
    path = file_info["path"]
    url = file_info["url"]

    set_update_status("downloading", "Downloading {}".format(path))
    content = http_get(url)

    ensure_parent_folders(path)

    with open(path, "wb") as f:
        f.write(content)


def check_for_update():
    try:
        set_update_status("checking", "Checking remote version...")

        raw = http_get(VERSION_URL)
        remote_data = ujson.loads(raw.decode())

        remote_version = remote_data.get("version", "0.0.0")
        local_version = get_local_version()

        if not is_newer(remote_version, local_version):
            set_update_status("idle", "Already up to date at version {}".format(local_version))
            return False

        files = remote_data.get("files", [])
        if not files:
            raise RuntimeError("Remote version.json has no files list")

        set_update_status("updating", "Updating from {} to {}".format(local_version, remote_version))

        for file_info in files:
            download_file(file_info)

        save_local_version(remote_version)
        set_update_status("complete", "Updated successfully to version {}".format(remote_version))

        utime.sleep(2)
        machine.reset()
        return True

    except Exception as ex:
        set_update_status("error", str(ex))
        raise
