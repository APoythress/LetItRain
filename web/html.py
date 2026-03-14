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

    # Pre-calc values for form
    enabled_num = 1 if schedule.get("enabled") else 0
    start_hour = schedule.get("start_hour", 6)
    start_minute = schedule.get("start_minute", 0)
    appt_value = "{:02d}:{:02d}".format(start_hour, start_minute)
    duration = schedule.get("duration_minutes", 10)

    checked_mon = "checked" if 0 in days else ""
    checked_tue = "checked" if 1 in days else ""
    checked_wed = "checked" if 2 in days else ""
    checked_thu = "checked" if 3 in days else ""
    checked_fri = "checked" if 4 in days else ""
    checked_sat = "checked" if 5 in days else ""
    checked_sun = "checked" if 6 in days else ""

    enabled_yes_selected = "selected" if enabled_num == 1 else ""
    enabled_no_selected = "selected" if enabled_num == 0 else ""

    return """<!DOCTYPE html>
<html>

<head>
    <meta charset="utf-8">
    <title>Pico Sprinkler</title>
    <style>

        body {{
            font-family: Arial, sans-serif;
            margin: 24px;
            line-height: 1.4;
        }}

        .card {{
            border: 1px solid #ccc;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
        }}

        .status {{
            display: flex;
            flex-direction: column;
            flex-basis: 100%;
        }}

        .columns {{
            columns: 3 auto;
        }}

        .columns p {{
            margin: 2px;
            padding-bottom: 5%;
        }}
        
        .history {{}}

        .btn {{
            display: inline-block;
            padding: 10px 14px;
            border: 1px solid #444;
            text-decoration: none;
            margin-right: 8px;
            border-radius: 6px;
            color: #111;
        }}

        input[type="number"],
        input[type="text"] {{
            width: 90px;
        }}

        /* Custom phone CSS */
        @media only screen and (max-width: 600px) {{
            .columns {{
                columns: 2 auto;
            }}
        }}
    </style>
</head>

<body>
    <h1>{device_name}</h1>

    <div class="card status">
        <h2>Status</h2>
        <div class="columns">
            <div>
                <p><strong>Current time:</strong> {now_iso}</p>
                <p><strong>Status:</strong> {status}</p>
            </div>
            <div>
                <p><strong>Current mode:</strong> {current_run_mode}</p>
                <p><strong>Current run ends:</strong> {current_end}</p>
            </div>
            <div>
                <p><strong>Last action:</strong> {last_action}</p>
                <p><strong>Next run:</strong> {next_run}</p>
            </div>
        </div>
    </br>
        <div>
            <a class="btn" href="/start">Start Now</a>
            <a class="btn" href="/stop">Stop Now</a>
            <a class="btn" href="/update">Check For Update</a>
            <a class="btn" href="/sync-rtc">Sync RTC</a>
        </div>
    </div>

    <div class="card">
        <h2>Schedule: {enabled}</h2> 
        <p style="font-style: italic;"><strong>Days:</strong> {days} | <strong>Start:</strong> {start_time} | <strong>Duration:</strong> {duration} min</p>
        
        <div class="">
            <form action="/save" method="get">
                <p>
                    <label>Enable Schedule? </label>
                    <select name="enabled">
                        <option value="1" {enabled_yes_selected}>Yes</option>
                        <option value="0" {enabled_no_selected}>No</option>
                    </select>
                </p>

                <p>
                    <label>Days: </label>
                    <label><input type="checkbox" name="days" value="0" {checked_mon}>Mon</label>
                    <label><input type="checkbox" name="days" value="1" {checked_tue}>Tue</label>
                    <label><input type="checkbox" name="days" value="2" {checked_wed}>Wed</label>
                    <label><input type="checkbox" name="days" value="3" {checked_thu}>Thur</label>
                    <label><input type="checkbox" name="days" value="4" {checked_fri}>Fri</label>
                    <label><input type="checkbox" name="days" value="5" {checked_sat}>Sat</label>
                    <label><input type="checkbox" name="days" value="6" {checked_sun}>Sun</label>
                </p>
                
                <p>
                    <label for="appt">Select a time:</label>
                    <input type="time" id="appt" name="appt" value="{appt_value}">
                </p>

                <p>
                    <label>Duration: <input name="duration" type="number" min="1" max="240" value="{duration}"></label>
                </p>

                <p><button type="submit">Save Schedule</button></p>
            </form>
        </div>
    </div>

    <div class="card">
        <h2>Software</h2>
        <p><strong>Installed Version:</strong> {local_version}</p>
        <p><strong>Update Status:</strong> {update_state}</p>
        <p><strong>Message:</strong> {update_message}</p>
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

        # Status
        status=state.status,
        current_run_mode=state.current_run_mode or "None",
        current_end=epoch_to_iso(current_end),
        last_action=state.last_action,
        next_run=epoch_to_iso(next_run_epoch),
        enabled="Yes" if schedule.get("enabled") else "No",

        # Schedule form / display
        days=day_text,
        start_time=hhmm_string(start_hour, start_minute),
        duration=duration,
        appt_value=appt_value,
        enabled_yes_selected=enabled_yes_selected,
        enabled_no_selected=enabled_no_selected,
        checked_mon=checked_mon,
        checked_tue=checked_tue,
        checked_wed=checked_wed,
        checked_thu=checked_thu,
        checked_fri=checked_fri,
        checked_sat=checked_sat,
        checked_sun=checked_sun,

        # Software
        local_version=local_version,
        update_state=update_state,
        update_message=update_message,

        # History data
        last_start=epoch_to_iso(last_run.get("start_epoch")),
        last_end=epoch_to_iso(last_run.get("end_epoch")),
        last_mode=last_run.get("mode") or "None",
        last_status=last_run.get("status") or "None",
    )
