from machine import I2C

DS3231_ADDR = 0x68

def _bcd_to_dec(value):
    return ((value >> 4) * 10) + (value & 0x0F)

def _dec_to_bcd(value):
    return ((value // 10) << 4) | (value % 10)

class DS3231:
    def __init__(self, i2c, address=DS3231_ADDR):
        self.i2c = i2c
        self.address = address

    def datetime_tuple(self):
        data = self.i2c.readfrom_mem(self.address, 0x00, 7)
        second = _bcd_to_dec(data[0] & 0x7F)
        minute = _bcd_to_dec(data[1] & 0x7F)
        hour = _bcd_to_dec(data[2] & 0x3F)
        weekday = _bcd_to_dec(data[3] & 0x07)
        day = _bcd_to_dec(data[4] & 0x3F)
        month = _bcd_to_dec(data[5] & 0x1F)
        year = 2000 + _bcd_to_dec(data[6])
        return (year, month, day, hour, minute, second, weekday)

    def set_datetime(self, year, month, day, hour, minute, second, weekday=1):
        payload = bytes([
            _dec_to_bcd(second),
            _dec_to_bcd(minute),
            _dec_to_bcd(hour),
            _dec_to_bcd(weekday),
            _dec_to_bcd(day),
            _dec_to_bcd(month),
            _dec_to_bcd(year - 2000),
        ])
        self.i2c.writeto_mem(self.address, 0x00, payload)

    def epoch(self):
        import utime
        y, mo, d, h, mi, s, _wd = self.datetime_tuple()
        return utime.mktime((y, mo, d, h, mi, s, 0, 0))

    def iso_string(self):
        y, mo, d, h, mi, s, _wd = self.datetime_tuple()
        print("{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(y, mo, d, h, mi, s))
        return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(y, mo, d, h, mi, s)
