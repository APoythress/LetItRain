# core/scheduler.py
# Multi-zone scheduler.
#
# The schedule structure (from config.json / Firebase) is:
#
#   schedule:
#     monday:
#       enabled: true
#       slots: [
#         {zone: 1, start_hour: 5, start_minute: 0,  duration_minutes: 15},
#         {zone: 2, start_hour: 5, start_minute: 15, duration_minutes: 15},
#       ]
#     tuesday: ...
#
# The scheduler finds the next slot that should fire right now.
# "Right now" means: start_hour:start_minute matches the current time
# within a 30-second window, and this slot hasn't already run today.
#
# last_run_slots tracks {slot_key: epoch} so we don't double-fire.
# slot_key = "monday_0", "monday_1", etc.
#
# now_epoch/local_epoch args are always the shifted "local wall clock epoch"
# from core/unix_time.py's local_wall_clock_epoch() -- time.gmtime() on that
# value yields local wall-clock fields directly, same trick the MicroPython
# build used, just computed via zoneinfo now instead of a fixed offset.

import time


DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday",
             "friday", "saturday", "sunday"]


def _today_name(now_tuple):
    """Return lowercase day name for the given time.gmtime() tuple."""
    # tm_wday: 0=Mon … 6=Sun
    return DAY_NAMES[now_tuple[6]]


def _slot_key(day_name, index):
    return "{}_{}".format(day_name, index)


def get_pending_slot(schedule, state, last_run_slots, now_epoch):
    """
    Return the next schedule slot that should fire right now, or None.

    Args:
        schedule:       dict — the full schedule subtree from config
        state:          ControllerState — current run state
        last_run_slots: dict — {slot_key: epoch} of slots already run today
        now_epoch:      int — current Unix epoch

    Returns:
        (slot_dict, slot_key) or (None, None)
    """
    if state.is_running():
        return None, None   # never interrupt an active run

    now_tuple   = time.gmtime(now_epoch)
    today       = _today_name(now_tuple)
    day_schedule = schedule.get(today, {})

    if not day_schedule.get("enabled", False):
        return None, None

    slots = day_schedule.get("slots", [])
    current_hour   = now_tuple[3]
    current_minute = now_tuple[4]
    current_second = now_tuple[5]

    for i, slot in enumerate(slots):
        key = _slot_key(today, i)

        # Already ran this slot today?
        if key in last_run_slots:
            continue

        slot_hour   = slot.get("start_hour", 0)
        slot_minute = slot.get("start_minute", 0)

        # Match within a 30-second window after the scheduled start
        if current_hour != slot_hour or current_minute != slot_minute:
            continue
        if current_second > 30:
            continue   # past the fire window; will not re-fire

        return slot, key

    return None, None


def get_next_slot(schedule, last_run_slots, now_epoch):
    """
    Return the next upcoming enabled slot from now, looking up to 7 days
    ahead -- for display only (e.g. the LCD's "next" field). Independent
    of get_pending_slot(): this never decides whether to fire a run, just
    what's coming up next.

    Returns (day_name, hour, minute, zone_id), or None if no day has any
    enabled slots at all.
    """
    now_tuple       = time.gmtime(now_epoch)
    current_weekday = now_tuple[6]  # 0=Mon..6=Sun
    current_hour    = now_tuple[3]
    current_minute  = now_tuple[4]

    best = None  # (day_offset, hour, minute, day_name, zone_id)

    for offset in range(7):
        weekday      = (current_weekday + offset) % 7
        day_name     = DAY_NAMES[weekday]
        day_schedule = schedule.get(day_name, {})
        if not day_schedule.get("enabled", False):
            continue

        for i, slot in enumerate(day_schedule.get("slots", [])):
            hour   = slot.get("start_hour", 0)
            minute = slot.get("start_minute", 0)

            if offset == 0:
                if (hour, minute) < (current_hour, current_minute):
                    continue  # already passed today
                if _slot_key(day_name, i) in last_run_slots:
                    continue  # already ran today

            candidate = (offset, hour, minute)
            if best is None or candidate < (best[0], best[1], best[2]):
                best = (offset, hour, minute, day_name, slot.get("zone", 1))

    if best is None:
        return None
    _, hour, minute, day_name, zone_id = best
    return day_name, hour, minute, zone_id


def clear_old_slot_runs(last_run_slots, now_epoch):
    """
    Purge slots from last_run_slots that were recorded yesterday or earlier.
    Called once per main loop iteration to prevent the dict growing forever.
    """
    today_midnight = now_epoch - (now_epoch % 86400)
    stale = [k for k, v in last_run_slots.items() if v < today_midnight]
    for k in stale:
        del last_run_slots[k]
