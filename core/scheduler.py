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

import utime


DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday",
             "friday", "saturday", "sunday"]


def _today_name(now_tuple):
    """Return lowercase day name for the given utime.localtime() tuple."""
    # utime weekday: 0=Mon … 6=Sun
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

    now_tuple   = utime.localtime(now_epoch)
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


def clear_old_slot_runs(last_run_slots, now_epoch):
    """
    Purge slots from last_run_slots that were recorded yesterday or earlier.
    Called once per main loop iteration to prevent the dict growing forever.
    """
    today_midnight = now_epoch - (now_epoch % 86400)
    stale = [k for k, v in last_run_slots.items() if v < today_midnight]
    for k in stale:
        del last_run_slots[k]
