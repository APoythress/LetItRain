# hardware/lcd1602.py
# 16x2 character LCD (HD44780-compatible controller) driven over the
# Adafruit Character LCD Backpack's SPI/shift-register mode, which
# exposes DAT/CLK/LAT instead of I2C SDA/SCL. That backpack is a 74HC595
# shift register wired to the HD44780's RS/Enable/D4-D7/backlight lines
# (RW is tied low on the backpack itself -- write-only).
#
# The shift register's 8 outputs map to (bit7 shifted out first):
#   bit7  unused (RW, tied low)  bit3  D6
#   bit6  backlight (1=on)       bit2  D7
#   bit5  D4                     bit1  Enable
#   bit4  D5                     bit0  RS (0=command, 1=character data)
# Verified directly against Adafruit's own reference implementation
# (adafruit_character_lcd/character_lcd_spi.py's ShiftRegister74HC595
# pin assignment: get_pin(0..6) => RS, Enable, D7, D6, D5, D4,
# backlight).
#
# Every register update is: LAT low, shift the byte out MSB-first while
# pulsing CLK once per bit, then LAT high (rising edge copies the shift
# register into the output latches, which is what the LCD actually sees).
#
# Ported from machine.Pin/utime to gpiozero.OutputDevice/time -- the
# bit-banging logic itself (shift/latch/nibble sequencing, timing) is
# unchanged.

from gpiozero import OutputDevice
import time

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
        self._dat = OutputDevice(dat_pin)
        self._clk = OutputDevice(clk_pin)
        self._lat = OutputDevice(lat_pin)
        self._backlight = 0x40  # bit6, on by default -- see module header for bit mapping
        self._init_display()

    # ------------------------------------------------------------------
    # Shift-register primitives
    # ------------------------------------------------------------------

    def _shift_out(self, byte):
        for i in range(7, -1, -1):
            self._dat.value = (byte >> i) & 1
            self._clk.on()
            self._clk.off()

    def _latch(self, byte):
        self._lat.off()
        self._shift_out(byte)
        self._lat.on()

    def _write_nibble(self, rs, nibble):
        # nibble bit0->D4, bit1->D5, bit2->D6, bit3->D7 per the standard
        # HD44780 4-bit protocol; see module header for the register bits
        # each of those lands on.
        base = (
            self._backlight
            | (rs << 0)
            | ((nibble & 0x01) << 5)   # D4
            | ((nibble & 0x02) << 3)   # D5
            | ((nibble & 0x04) << 1)   # D6
            | ((nibble & 0x08) >> 1)   # D7
        )
        self._latch(base)          # EN=0, data+RS settled
        self._latch(base | 0x02)   # EN=1 -- HD44780 samples while high
        time.sleep(2e-6)
        self._latch(base)          # EN=0 -- falling edge latches the nibble
        time.sleep(2e-6)

    def _write_byte(self, rs, value, exec_delay_us=50):
        self._write_nibble(rs, (value >> 4) & 0x0F)
        self._write_nibble(rs, value & 0x0F)
        time.sleep(exec_delay_us * 1e-6)

    def _command(self, cmd, exec_delay_us=50):
        self._write_byte(0, cmd, exec_delay_us)

    def _data(self, value):
        self._write_byte(1, value)

    # ------------------------------------------------------------------
    # Init / public API
    # ------------------------------------------------------------------

    def _init_display(self):
        time.sleep(0.05)  # HD44780 power-on settle time
        # Force into a known state regardless of whatever mode the
        # controller powered up in -- this backpack has no reset pin, so
        # this datasheet-mandated nibble sequence is the only way to
        # guarantee it's actually in 4-bit mode afterward.
        self._write_nibble(0, 0x03)
        time.sleep(4500e-6)
        self._write_nibble(0, 0x03)
        time.sleep(4500e-6)
        self._write_nibble(0, 0x03)
        time.sleep(150e-6)
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
        self._backlight = 0x40 if on else 0x00
        self._latch(self._backlight)
