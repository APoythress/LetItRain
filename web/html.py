from core.time_utils import epoch_to_iso, hhmm_string, DAY_NAMES
import ujson

# Helpers for version and update status
def get_local_version():
    try:
        with open("version.json", "r") as f:
            data = ujson.load(f)
            return data.get("version", "0.0.0")
    except:
        return "unknown"

def get_update_status():
    try:
        with open("update_status.json", "r") as f:
            return ujson.load(f)
    except:
        return {
            "status": "unknown",
            "message": "No update status available."
        }


def render_dashboard(config, state, now_iso, next_run_epoch):
    schedule = config.get("schedule", {})
    days = schedule.get("days", [])
    day_text = ", ".join(DAY_NAMES[d] for d in days) if days else "None"

    last_run = config.get("last_run", {})
    current_end = state.run_end_epoch()

    # Version / update
    local_version = get_local_version()
    update_status = get_update_status()
    update_state = update_status.get("status", "unknown")
    update_message = update_status.get("message", "")

    local_version=local_version,
    update_state=update_state,
    update_message=update_message,

    return """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Pico Sprinkler</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 24px; line-height: 1.4; }}
        .card {{ border: 1px solid #ccc; border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
        .btn {{ display:inline-block; padding:10px 14px; border:1px solid #444; text-decoration:none; margin-right:8px; border-radius:6px; color:#111; }}
        input[type="number"], input[type="text"] {{ width: 90px; }}
    </style>
</head>
<body>
    <h1>{device_name}</h1>

    <div class="card">
        <h2>Status</h2>
        <p><strong>Current time:</strong> {now_iso}</p>
        <p><strong>Status:</strong> {status}</p>
        <p><strong>Current mode:</strong> {current_run_mode}</p>
        <p><strong>Current run ends:</strong> {current_end}</p>
        <p><strong>Last action:</strong> {last_action}</p>
        <p><strong>Next run:</strong> {next_run}</p>
        <a class="btn" href="/start">Start Now</a>
        <a class="btn" href="/stop">Stop Now</a>
        <a class="btn" href"/update">Check For Update</a>
    </div>

    <div class="card">
        <h2>Schedule</h2>
        <p><strong>Enabled:</strong> {enabled}</p>
        <p><strong>Days:</strong> {days}</p>
        <p><strong>Start:</strong> {start_time}</p>
        <p><strong>Duration:</strong> {duration} min</p>

        <form action="/save" method="get">
            <p><label>Enabled (1 or 0): <input name="enabled" type="number" min="0" max="1" value="{enabled_num}"></label></p>
            <p><label>Days CSV (0-6 Mon-Sun): <input name="days" type="text" value="{days_csv}"></label></p>
            <p><label>Hour: <input name="hour" type="number" min="0" max="23" value="{hour}"></label></p>
            <p><label>Minute: <input name="minute" type="number" min="0" max="59" value="{minute}"></label></p>
            <p><label>Duration: <input name="duration" type="number" min="1" max="240" value="{duration}"></label></p>
            <p><button type="submit">Save Schedule</button></p>
        </form>
    </div>

    <div class="card">
        <h2>Last Run</h2>
        <p><strong>Last start:</strong> {last_start}</p>
        <p><strong>Last end:</strong> {last_end}</p>
        <p><strong>Last mode:</strong> {last_mode}</p>
        <p><strong>Last status:</strong> {last_status}</p>
    </div>
</body>
</html>""".format(
        device_name=config.get("device_name", "Pico Sprinkler"),
        now_iso=now_iso,
        status=state.status,
        current_run_mode=state.current_run_mode or "None",
        current_end=epoch_to_iso(current_end),
        last_action=state.last_action,
        next_run=epoch_to_iso(next_run_epoch),
        enabled="Yes" if schedule.get("enabled") else "No",
        enabled_num=1 if schedule.get("enabled") else 0,
        days=day_text,
        days_csv=",".join(str(d) for d in days),
        start_time=hhmm_string(schedule.get("start_hour", 6), schedule.get("start_minute", 0)),
        hour=schedule.get("start_hour", 6),
        minute=schedule.get("start_minute", 0),
        duration=schedule.get("duration_minutes", 10),
        last_start=epoch_to_iso(last_run.get("start_epoch")),
        last_end=epoch_to_iso(last_run.get("end_epoch")),
        last_mode=last_run.get("mode") or "None",
        last_status=last_run.get("status") or "None",
    )
