import ujson

CONFIG_PATH = "config.json"

def default_config():
    return {
        "device_name": "Pico Sprinkler Controller",
        "relay_pin": 15,
        "relay_active_high": True,
        "manual_default_duration_minutes": 10,
        "schedule": {
            "enabled": False,
            "days": [],
            "start_hour": 6,
            "start_minute": 0,
            "duration_minutes": 10
        },
        "last_run": {
            "start_epoch": None,
            "end_epoch": None,
            "mode": None,
            "status": None
        }
    }

def load_config(path=CONFIG_PATH):
    try:
        with open(path, "r") as f:
            return ujson.load(f)
    except OSError:
        cfg = default_config()
        save_config(cfg, path)
        return cfg

def save_config(config, path=CONFIG_PATH):
    with open(path, "w") as f:
        ujson.dump(config, f)
