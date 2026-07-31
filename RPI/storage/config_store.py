# storage/config_store.py
# Persists config to disk as JSON.
#
# Writes go through a temp-file-then-os.replace() pattern: a raw
# open(path, "w") that gets interrupted mid-write (power loss, an
# ungraceful shutdown) can leave config.json truncated or corrupt on next
# boot -- a real risk on a full Linux/SD-card device in a way it wasn't on
# the Pico's flash filesystem. os.replace() is atomic on POSIX, so the
# on-disk file is always either the old complete version or the new
# complete version, never a partial write.

import json
import os

CONFIG_PATH = "config.json"


def load_config():
    """Load config from disk. Returns empty dict on any error."""
    try:
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    except Exception as ex:
        print("config_store: load failed:", ex)
        return {}


def save_config(config):
    """Persist config dict to disk atomically."""
    tmp_path = CONFIG_PATH + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(config, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, CONFIG_PATH)
        return True
    except Exception as ex:
        print("config_store: save failed:", ex)
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return False
