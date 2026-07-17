# update/updater.py
# Over-the-air firmware updates via Firebase Cloud Storage.
#
# Flow:
#   1. Download ota/manifest.json from Storage: {"version": "1.3.0", "files": [{"path": "main.py"}, ...]}
#   2. Compare manifest version to local version.json
#   3. If newer, download every listed file from ota/{version}/{path} to its
#      on-device path, then overwrite local version.json.
#
# This module only ever reads from Storage — updates are published by
# uploading new files to the bucket yourself (Firebase Console or gsutil),
# there is no write path here.
#
# Reuses the Firebase ID token from the already-authenticated FirebaseClient
# (RTDB and Storage both accept the same Firebase Auth ID token) rather than
# signing in separately.

import ujson
import os
import gc

try:
    import urequests as requests
except ImportError:
    import requests  # fallback for local testing

LOCAL_VERSION_FILE = "version.json"
UPDATE_STATUS_FILE = "update_status.json"
MANIFEST_PATH       = "ota/manifest.json"
_REQUEST_TIMEOUT    = 15  # firmware files are small, but allow more than RTDB's 8s
_DOWNLOAD_CHUNK_SIZE = 512  # read/write in small pieces so we never need one
                             # big contiguous allocation for the whole file


def _storage_url(bucket, object_path):
    # Firebase Storage REST API requires the object path's slashes to be
    # percent-encoded, since they're part of the object name, not a real path.
    encoded = object_path.replace("/", "%2F")
    return "https://firebasestorage.googleapis.com/v0/b/{}/o/{}?alt=media".format(
        bucket, encoded
    )


def _set_status(status, message):
    try:
        with open(UPDATE_STATUS_FILE, "w") as f:
            ujson.dump({"status": status, "message": message}, f)
    except Exception:
        pass  # diagnostic only, never fatal


def get_status():
    """Current OTA status, for forwarding to Firebase so the app can show progress."""
    try:
        with open(UPDATE_STATUS_FILE, "r") as f:
            return ujson.load(f)
    except Exception:
        return {"status": "idle", "message": "No update attempted yet."}


def get_local_version():
    try:
        with open(LOCAL_VERSION_FILE, "r") as f:
            return ujson.load(f).get("version", "0.0.0")
    except Exception:
        return "0.0.0"


def _save_local_version(version):
    with open(LOCAL_VERSION_FILE, "w") as f:
        ujson.dump({"version": version}, f)


def _parse_version(v):
    return [int(x) for x in v.split(".")]


def _is_newer(remote_version, local_version):
    return _parse_version(remote_version) > _parse_version(local_version)


def _ensure_parent_dirs(path):
    parts = path.split("/")[:-1]
    current = ""
    for part in parts:
        current = current + "/" + part if current else part
        try:
            os.mkdir(current)
        except OSError:
            pass  # already exists


def _get(bucket, id_token, object_path):
    url = requests.get(
        _storage_url(bucket, object_path),
        headers={"Authorization": "Firebase {}".format(id_token)},
        timeout=_REQUEST_TIMEOUT,
    )
    return url


def _download_file(bucket, id_token, object_path, local_path):
    resp = _get(bucket, id_token, object_path)
    if resp.status_code != 200:
        body = resp.text
        resp.close()
        raise RuntimeError("download {} failed: {} {}".format(
            object_path, resp.status_code, body))
    _ensure_parent_dirs(local_path)
    try:
        # Stream straight to disk in small pieces instead of resp.content,
        # which buffers the whole file as one contiguous bytes object and
        # blows up with "memory allocation failed" once the heap is
        # fragmented (Wi-Fi buffers, HTTP server thread, relay/RTC objects
        # all share the same ~264KB SRAM).
        with open(local_path, "wb") as f:
            while True:
                chunk = resp.raw.read(_DOWNLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                f.write(chunk)
                gc.collect()
    finally:
        resp.close()


def check_for_update(bucket, id_token):
    """
    Check Firebase Storage for a newer firmware version and, if found,
    download every file it lists to its on-device path.

    Does NOT reset the board — the caller decides when it's safe to do so
    (e.g. not mid-irrigation-cycle).

    Returns True if a new version was downloaded (caller should reset once
    safe), False if already up to date or the check failed.
    """
    resp = None
    try:
        _set_status("checking", "Checking for update...")
        resp = _get(bucket, id_token, MANIFEST_PATH)
        if resp.status_code != 200:
            status_code = resp.status_code
            _set_status("error", "manifest fetch failed: {} {}".format(
                status_code, resp.text))
            return False
        manifest = resp.json()
        resp.close()
        resp = None
        gc.collect()

        remote_version = manifest.get("version", "0.0.0")
        local_version  = get_local_version()

        if not _is_newer(remote_version, local_version):
            _set_status("idle", "Up to date at {}".format(local_version))
            return False

        files = manifest.get("files", [])
        if not files:
            _set_status("error", "manifest for {} has no files".format(remote_version))
            return False

        _set_status("updating", "Updating {} -> {}".format(local_version, remote_version))
        for entry in files:
            path = entry["path"]  # same relative path in Storage and on-device
            _set_status("downloading", "Downloading {}".format(path))
            _download_file(bucket, id_token, "ota/{}/{}".format(remote_version, path), path)

        _save_local_version(remote_version)
        _set_status("staged", "Downloaded {} — waiting for a safe moment to reboot".format(
            remote_version))
        return True

    except Exception as ex:
        _set_status("error", str(ex))
        return False
    finally:
        if resp is not None:
            resp.close()
