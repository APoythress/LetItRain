# hardware/lcd1602.py
# 16x2 character LCD (HD44780-compatible controller) driven over the
# Adafruit Character LCD Backpack's SPI/shift-register mode, which
# exposes DAT/CLK/LAT instead of I2C SDA/SCL. That backpack is a 74HC595
# shift register wired to the HD44780's RS/Enable/D4-D7/backlight lines
# (RW is tied low on the backpack itself -- write-only).
#
# The shift register's 8 outputs map to (bit7 shifted out first):
#   bit7  backlight (1=on)      bit3  D7
#   bit6  D4                    bit2  Enable
#   bit5  D5                    bit1  RS (0=command, 1=character data)
#   bit4  D6                    bit0  unused (RW, tied low)
# This mapping was reverse-engineered from Adafruit's own
# Adafruit_LiquidCrystal library (its SPI constructor's pin assignments),
# not copied from it -- this is a fresh bit-banged implementation.
#
# Every register update is: LAT low, shift the byte out MSB-first while
# pulsing CLK once per bit, then LAT high (rising edge copies the shift
# register into the output latches, which is what the LCD actually sees).

from machine import Pin
import utime

_CLEAR_DISPLAY   = 0x01
_ENTRY_MODE_SET  = 0x04
_DISPLAY_CONTROL = 0x08
_FUNCTION_SET    = 0x20
_SET_DDRAM_ADDR  = 0x80

_ENTRY_LEFT_INCREMENT = 0x02
_DISPLAY_ON  = 0x04
_4BIT_MODE   = 0x00
_2LINE       = 0x08
_5x8_DOTS    = 0x00

_ROW_OFFSETS = (0x00, 0x40)  # 16x2 only


class LCD1602:
    def __init__(self, dat_pin, clk_pin, lat_pin):
        self._dat = Pin(dat_pin, Pin.OUT)
        self._clk = Pin(clk_pin, Pin.OUT)
        self._lat = Pin(lat_pin, Pin.OUT)
        self._backlight = 0x80  # on by default
        self._init_display()

    # ------------------------------------------------------------------
    # Shift-register primitives
    # ------------------------------------------------------------------

    def _shift_out(self, byte):
        for i in range(7, -1, -1):
            self._dat.value((byte >> i) & 1)
            self._clk.value(1)
            self._clk.value(0)

    def _latch(self, byte):
        self._lat.value(0)
        self._shift_out(byte)
        self._lat.value(1)

    def _write_nibble(self, rs, nibble):
        # nibble bit0->D4, bit1->D5, bit2->D6, bit3->D7 per the standard
        # HD44780 4-bit protocol; see module header for the register bits
        # each of those lands on.
        base = (
            self._backlight
            | (rs << 1)
            | ((nibble & 0x01) << 6)   # D4
            | ((nibble & 0x02) << 4)   # D5
            | ((nibble & 0x04) << 2)   # D6
            | ((nibble & 0x08) << 0)   # D7
        )
        self._latch(base)          # EN=0, data+RS settled
        self._latch(base | 0x04)   # EN=1 -- HD44780 samples while high
        utime.sleep_us(2)
        self._latch(base)          # EN=0 -- falling edge latches the nibble
        utime.sleep_us(2)

    def _write_byte(self, rs, value, exec_delay_us=50):
        self._write_nibble(rs, (value >> 4) & 0x0F)
        self._write_nibble(rs, value & 0x0F)
        utime.sleep_us(exec_delay_us)

    def _command(self, cmd, exec_delay_us=50):
        self._write_byte(0, cmd, exec_delay_us)

    def _data(self, value):
        self._write_byte(1, value)

    # ------------------------------------------------------------------
    # Init / public API
    # ------------------------------------------------------------------

    def _init_display(self):
        utime.sleep_ms(50)  # HD44780 power-on settle time
        # Force into a known state regardless of whatever mode the
        # controller powered up in -- this backpack has no reset pin, so
        # this datasheet-mandated nibble sequence is the only way to
        # guarantee it's actually in 4-bit mode afterward.
        self._write_nibble(0, 0x03)
        utime.sleep_us(4500)
        self._write_nibble(0, 0x03)
        utime.sleep_us(4500)
        self._write_nibble(0, 0x03)
        utime.sleep_us(150)
        self._write_nibble(0, 0x02)  # now actually in 4-bit mode

        self._command(_FUNCTION_SET | _4BIT_MODE | _2LINE | _5x8_DOTS)
        self._command(_DISPLAY_CONTROL | _DISPLAY_ON)
        self.clear()
        self._command(_ENTRY_MODE_SET | _ENTRY_LEFT_INCREMENT)

    def clear(self):
        self._command(_CLEAR_DISPLAY, exec_delay_us=2000)

    def set_cursor(self, col, row):
        row = min(row, len(_ROW_OFFSETS) - 1)
        self._command(_SET_DDRAM_ADDR | (col + _ROW_OFFSETS[row]))

    def write_text(self, text):
        for ch in text:
            self._data(ord(ch))

    def set_backlight(self, on):
        self._backlight = 0x80 if on else 0x00
        self._latch(self._backlight)
