# hardware/lcd1602.py
# 16x2 character LCD (HD44780-compatible controller) driven over the
# Adafruit Character LCD Backpack's I2C mode via its onboard MCP23008
# GPIO expander (I2C address 0x20 by default, set by the A0-A2 solder
# jumpers).
#
# Switched from the backpack's SPI/shift-register mode after the physical
# unit's SPI-enable solder jumper proved unreliable in practice -- despite
# looking bridged, i2cdetect kept finding the board still answering on I2C
# regardless of DAT/CLK/LAT wiring, power, or ground, all of which checked
# out fine. I2C mode needs no jumper/soldering on this board at all, and a
# bit-banged I2C test against the exact same DAT/CLK wiring (this
# backpack's terminal block doubles those pins as SDA/SCL in I2C mode)
# confirmed the display and backlight both work correctly over it.
#
# MCP23008 GPIO pin mapping for this backpack (matches Adafruit's own
# Adafruit_CharLCD reference driver):
#   GP0  unused
#   GP1  RS
#   GP2  Enable
#   GP3  D4
#   GP4  D5
#   GP5  D6
#   GP6  D7
#   GP7  Backlight (1=on)

import time

_MCP23008_IODIR = 0x00
_MCP23008_GPIO  = 0x09

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

_BACKLIGHT_BIT = 0x80  # GP7
_ENABLE_BIT    = 0x04  # GP2
_RS_BIT        = 0x02  # GP1


class LCD1602:
    def __init__(self, bus, address=0x20):
        """
        Args:
            bus:     an open smbus2.SMBus instance. Safe to share with
                     other I2C devices on the same bus (e.g. the DS3231
                     RTC) -- distinguished by address, not bus ownership.
            address: MCP23008 I2C address (0x20 default on this backpack).
        """
        self._bus = bus
        self._addr = address
        self._backlight = _BACKLIGHT_BIT  # on by default
        self._bus.write_byte_data(self._addr, _MCP23008_IODIR, 0x00)  # all 8 pins as outputs
        self._init_display()

    # ------------------------------------------------------------------
    # MCP23008 primitives
    # ------------------------------------------------------------------

    def _write_gpio(self, value):
        self._bus.write_byte_data(self._addr, _MCP23008_GPIO, value)

    def _write_nibble(self, rs, nibble):
        # nibble bit0->D4, bit1->D5, bit2->D6, bit3->D7 per the standard
        # HD44780 4-bit protocol -- all four land contiguously on GP3-GP6,
        # so a single left-shift maps the whole nibble at once.
        base = self._backlight | ((nibble & 0x0F) << 3) | (_RS_BIT if rs else 0)
        self._write_gpio(base | _ENABLE_BIT)   # EN=1 -- HD44780 samples while high
        self._write_gpio(base)                 # EN=0 -- falling edge latches the nibble

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
        # controller powered up in -- this datasheet-mandated nibble
        # sequence is the only way to guarantee it's actually in 4-bit
        # mode afterward.
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
        self._backlight = _BACKLIGHT_BIT if on else 0x00
        self._write_gpio(self._backlight)
