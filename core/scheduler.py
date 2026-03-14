import utime

def should_start_now(schedule, now_epoch, state, last_run_start_epoch):
    if not schedule.get("enabled", False):
        return False

    now = utime.localtime(now_epoch)
    weekday = now[6]
    hour = now[3]
    minute = now[4]

    if weekday not in schedule.get("days", []):
        return False

    if hour != schedule.get("start_hour", 6):
        return False

    if minute != schedule.get("start_minute", 0):
        return False

    if state.is_running():
        return False

    # prevent retriggering repeatedly inside the same minute
    if last_run_start_epoch is not None and abs(now_epoch - last_run_start_epoch) < 60:
        return False

    return True

def should_stop_now(now_epoch, state):
    if not state.is_running():
        return False
    end_epoch = state.run_end_epoch()
    return end_epoch is not None and now_epoch >= end_epoch

def next_run_epoch(schedule, now_epoch):
    if not schedule.get("enabled", False):
        return None

    allowed_days = schedule.get("days", [])
    if not allowed_days:
        return None

    start_hour = schedule.get("start_hour", 6)
    start_minute = schedule.get("start_minute", 0)

    for offset_days in range(0, 8):
        candidate_base = now_epoch + (offset_days * 86400)
        t = utime.localtime(candidate_base)
        weekday = t[6]
        if weekday not in allowed_days:
            continue

        candidate = utime.mktime((t[0], t[1], t[2], start_hour, start_minute, 0, 0, 0))
        if candidate >= now_epoch:
            return candidate

    return None
