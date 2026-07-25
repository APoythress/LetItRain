# storage/config_store.py
# Persists config to Pico flash as JSON.

import ujson


CONFIG_PATH = "config.json"


def load_config():
    """Load config from flash. Returns empty dict on any error."""
    try:
        with open(CONFIG_PATH, "r") as f:
            return ujson.load(f)
    except Exception as ex:
        print("config_store: load failed:", ex)
        return {}


def save_config(config):
    """Persist config dict to flash."""
    try:
        with open(CONFIG_PATH, "w") as f:
            ujson.dump(config, f)
        return True
    except Exception as ex:
        print("config_store: save failed:", ex)
        return False
