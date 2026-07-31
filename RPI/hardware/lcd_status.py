# hardware/lcd_status.py
# Composes the 16x2 status display: two lines, each split into a
# left-aligned and right-aligned field. Special states (booting,
# updating, error) instead show one centered message that replaces
# everything else.
#
# Each draw call only re-sends a row that actually changed text, since a
# full-row rewrite is 16 characters * 2 nibbles * 3 shift-register writes
# each -- cheap once, wasteful to repeat every main-loop pass for content
# that hasn't moved.

WIDTH = 16


def _row(left, right):
    left  = (left or "")[:WIDTH]
    right = (right or "")[:WIDTH]
    space = WIDTH - len(left) - len(right)
    if space < 0:
        right = right[:WIDTH - len(left)]
        space = 0
    return left + (" " * space) + right


def _center(text):
    text = (text or "")[:WIDTH]
    pad = WIDTH - len(text)
    left_pad = pad // 2
    return (" " * left_pad) + text + (" " * (pad - left_pad))


class LCDStatus:
    def __init__(self, lcd):
        self._lcd = lcd
        self._lines = [None, None]  # last-drawn text per row, for diffing

    def _draw_row(self, row, text):
        # str.ljust() doesn't exist in MicroPython's minimal string
        # implementation -- pad manually.
        text = text[:WIDTH]
        if len(text) < WIDTH:
            text = text + (" " * (WIDTH - len(text)))
        if text == self._lines[row]:
            return
        self._lines[row] = text
        self._lcd.set_cursor(0, row)
        self._lcd.write_text(text)

    def show_status(self, zone_text, next_text, ip_text, version_text):
        self._draw_row(0, _row(zone_text, version_text))
        self._draw_row(1, _row(next_text, ""))

    def show_message(self, message):
        """Single centered message, replacing all other content --
        booting, updating, and error states."""
        self._draw_row(0, _center(message))
        self._draw_row(1, " " * WIDTH)
