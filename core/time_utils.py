import utime

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

def epoch_to_iso(epoch):
    if epoch is None:
        return "None"
    t = utime.localtime(epoch)
    return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
        t[0], t[1], t[2], t[3], t[4], t[5]
    )

def hhmm_string(hour, minute):
    return "{:02d}:{:02d}".format(hour, minute)
