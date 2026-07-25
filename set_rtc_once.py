# Run this one time from the REPL or as main if you need to set the DS3231 clock.
# Update the values below, run it once, then you can remove or ignore the file.
#
# main.py auto-syncs the DS3231 from NTP every boot that has Wi-Fi, so this
# script is now only needed for a first boot with no internet available yet.
# Enter UTC time below, NOT your local time — main.py treats the DS3231 as
# UTC and applies the local offset (UTC_OFFSET_HOURS in secrets.py) only when
# matching the schedule, so a local time entered here would be shifted twice.

from machine import I2C, Pin
from hardware.ds3231 import DS3231

# year, month, day, hour, minute, second, weekday — all in UTC
# weekday: 1-7 for DS3231 register use
YEAR = 2026
MONTH = 3
DAY = 13
HOUR = 15
MINUTE = 41
SECOND = 0
WEEKDAY = 5

i2c = I2C(0, sda=Pin(0), scl=Pin(1), freq=100000)
rtc = DS3231(i2c)
rtc.set_datetime(YEAR, MONTH, DAY, HOUR, MINUTE, SECOND, WEEKDAY)
print("RTC set to:", rtc.iso_string())
