# GPIO Pinout — Raspberry Pi 3 A+

Single source of truth for wiring a new device. Pin numbers here must match
`config.json` (zones) and `main.py` (LCD/status LED/RTC construction) —
if you rewire to different GPIOs, update both, not just one.

## Summary (BCM numbering)

| Function          | BCM GPIO | Physical pin | Notes |
|--------------------|----------|---------------|-------|
| Zone 1 relay       | GPIO5    | 29            | `config.json` → `zones[0].pin` |
| Zone 2 relay       | GPIO6    | 31            | `config.json` → `zones[1].pin` |
| Zone 3 relay       | GPIO13   | 33            | `config.json` → `zones[2].pin` |
| Zone 4 relay       | GPIO19   | 35            | `config.json` → `zones[3].pin` |
| Zone 5 relay       | GPIO26   | 37            | `config.json` → `zones[4].pin` |
| Status LED (green) | GPIO23   | 16            | `main.py` → `StatusLED(green_pin=...)` |
| Status LED (red)   | GPIO24   | 18            | `main.py` → `StatusLED(..., red_pin=...)` |
| LCD backpack DAT/SDA | GPIO27 | 13            | I2C bus 3 (bit-banged) — see LCD section below |
| LCD backpack CLK/SCL | GPIO17 | 11            | I2C bus 3 (bit-banged) |
| LCD backpack LAT   | (unused) | —            | Only meaningful in SPI mode; not used in I2C mode |
| DS3231 RTC SDA      | GPIO2 (I2C1) | 3        | Optional — see RTC section |
| DS3231 RTC SCL      | GPIO3 (I2C1) | 5        | Optional |

Free/unused GPIOs at time of writing: 4, 7, 8, 9, 10, 11, 12, 14, 15, 16, 18,
20, 21, 22, 25. (11 was freed up when the LCD moved off SPI-style pins;
9/10 likewise.)

---

## Zone relays (5V relay board)

Each zone needs **three** connections to the Pi, not just signal + ground:

| Relay board pin | Connects to |
|-------------------|-------------|
| VCC                | Pi 5V (physical pin 2 or 4) — powers the relay board's driver circuitry and coils |
| GND                | Any Pi GND pin |
| IN1–IN5            | GPIO5, GPIO6, GPIO13, GPIO19, GPIO26 (one per zone, see table above) |

Notes:
- Most boards have a **JD-VCC jumper** near the VCC pin. Leave it in place (ties relay-coil power to the same VCC rail as the signal side) unless you specifically want electrical isolation between the Pi and the relay coils, in which case remove it and feed VCC/JD-VCC from two separate supplies.
- Current budget: ~70–80mA per energized relay. With all 5 zones potentially firing close together (auto-builder schedules), that's up to ~400mA on top of the Pi's own draw — use a real 5V/2.5A+ supply, not a marginal phone charger.
- `active_high` in `config.json` must match your board — most mechanical relay boards are **active-low** (`active_high: false`; energizes when the GPIO goes LOW), solid-state relay boards are usually active-high.
- The DS3231 RTC and this backpack's I2C mode are unrelated to relay wiring — no shared pins to worry about here.

---

## Status LED (green/red, boot & connectivity indicator)

Standard 5mm indicator LEDs, one per color:

```
GPIO23 (green) ──► 220–330Ω resistor ──► LED anode (long leg)
GPIO24 (red)   ──► 220–330Ω resistor ──► LED anode (long leg)
LED cathode (short leg, both) ──► any GND pin
```

GPIO drives HIGH = 3.3V, within spec for a standard LED + resistor — no
transistor needed. **Do not skip the resistor** — driving an LED directly
off a GPIO pin with no current limiting can damage the pin.

Behavior (see `hardware/status_led.py`):

| State | Green | Red |
|-------|-------|-----|
| Booting | flash 500ms on/off | off |
| Running normally | solid on | off |
| Running, no internet/Firebase | solid on | flash 5s on / 2s off |
| Boot failed | off | flash rapidly, 150ms on/off |

---

## LCD backpack — Adafruit I2C/SPI Character LCD Backpack (PID 292)

**This board runs in I2C mode, not SPI, despite the terminal block being
labeled LAT/DAT/CLK/3-5V/GND.** That labeling is a holdover from the board's
alternate SPI mode — DAT and CLK double as SDA/SCL in I2C mode (both with
onboard 10K pullups), and LAT is simply unused.

### Why I2C, not SPI

The backpack ships in I2C mode by default (an unsoldered "SPI Enable"
jumper on the front, near the A0–A2 address jumpers). Soldering that jumper
closed is supposed to switch it to SPI/shift-register mode — in practice,
on the unit this was validated against, that solder joint proved unreliable
(the board kept answering on I2C regardless of how it looked visually
soldered). I2C mode was confirmed to work cleanly with zero soldering risk,
so that's what the code (`hardware/lcd1602.py`) targets.

**For a new build: leave the SPI Enable jumper alone — do not solder it.**
Wire DAT/CLK straight to the Pi as described below and it works out of the box.

### Wiring

| Backpack terminal | Pi connection |
|---------------------|----------------|
| DAT                  | GPIO27 (physical pin 13) |
| CLK                  | GPIO17 (physical pin 11) |
| LAT                  | not connected (unused in I2C mode) |
| 3-5V                 | Pi 5V or 3.3V (either works — board accepts 3-5V) |
| GND                  | any Pi GND pin |

### Software requirement

DAT/CLK are wired as a **software (bit-banged) I2C bus**, separate from
the Pi's dedicated hardware I2C1 (which the DS3231 uses instead). This
needs a device-tree overlay in `/boot/firmware/config.txt`:

```
dtoverlay=i2c-gpio,bus=3,i2c_gpio_sda=27,i2c_gpio_scl=17
```

Verify after reboot:
```
ls /dev/i2c-3
i2cdetect -y 3   # should show a device at 0x20 -- the backpack's MCP23008
```

The backpack's onboard MCP23008 GPIO expander (I2C address `0x20` by
default) drives the actual HD44780 LCD lines. Pin mapping (matches
Adafruit's own `Adafruit_CharLCD` reference driver, see
`hardware/lcd1602.py`'s header comment for the full explanation):

| MCP23008 pin | HD44780 signal |
|--------------|-----------------|
| GP0          | unused |
| GP1          | RS |
| GP2          | Enable |
| GP3          | D4 |
| GP4          | D5 |
| GP5          | D6 |
| GP6          | D7 |
| GP7          | Backlight (1=on) |

The LCD is optional — if unwired, `main.py` logs `LCD init failed (not
wired?)` and continues without one.

---

## DS3231 RTC (optional)

Not strictly required — Raspberry Pi OS's `fake-hwclock` plus NTP
(`systemd-timesyncd`) already keep the system clock reasonably accurate
across reboots as long as the Pi has network access shortly after booting.
The RTC is only meaningfully better in the edge case of a reboot during an
extended network outage. `main.py` treats its absence as fully non-fatal.

If you do wire one:

| DS3231 pin | Pi connection |
|------------|----------------|
| SDA        | GPIO2, physical pin 3 (Pi's hardware I2C1) |
| SCL        | GPIO3, physical pin 5 |
| VCC        | 3.3V or 5V (module-dependent — check yours) |
| GND        | any GND pin |

This is the Pi's *dedicated* I2C1 bus (`/dev/i2c-1`), enabled via
`dtparam=i2c_arm=on` in `config.txt` — separate from the LCD's bit-banged
bus 3 above. Default address `0x68`. Verify with `i2cdetect -y 1`.

---

## `config.txt` summary

Everything above that needs a boot-time device-tree change, in one place:

```
dtparam=i2c_arm=on                                        # DS3231 (I2C1)
dtparam=watchdog=on                                        # systemd hardware watchdog
dtoverlay=i2c-gpio,bus=3,i2c_gpio_sda=27,i2c_gpio_scl=17    # LCD (bit-banged I2C)
```

Plus, once, in `/etc/systemd/system.conf`:
```
RuntimeWatchdogSec=30
```

See `deploy/README.md` for the full first-boot setup sequence these fit into.
