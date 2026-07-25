# Setup Checklist

## Relay wiring pinout (Pico 2)

Control-side wiring for a relay module with GND / DC+ / DC- / IN terminals.
GPIO numbering is identical between the original Pico and Pico 2 (same
40-pin castellated layout), so this applies to both.

| Relay pin | Connects to | Notes |
|---|---|---|
| **IN** (per channel) | Zone's GPIO — see table below | 3.3V logic signal from the Pico |
| **GND** | Any Pico **GND** pin | Common ground — required for the IN signal to be readable |
| **DC+** | 5V supply | Powers the relay coil driver |
| **DC-** | Same 5V supply's return | Pairs with DC+ |

### Per-zone IN pin mapping (matches `config.json`)

| Zone | GPIO | Pico 2 physical pin |
|---|---|---|
| Zone 1 | GP15 | 20 |
| Zone 2 | GP14 | 19 |
| Zone 3 | GP13 | 17 |
| Zone 4 | GP12 | 16 |
| Zone 5 | GP11 | 15 |

Only enable as many zones in `config.json` as you have relay channels wired.

### Power

- Each relay coil draws roughly 70-80mA when energized. Firmware only ever
  energizes **one zone at a time** (`core/state.py` tracks a single
  `current_zone_id`; `main.py` stops the active zone before starting another),
  so peak coil draw is always a single channel's worth, regardless of zone
  count.
- Prefer an external 5V supply for relay DC+/DC- once more than 1-2 zones
  are wired, rather than the Pico's VBUS (pin 40, USB-derived, ~500mA total
  budget shared with the Pico itself).
- Do not power the relay coil side from the Pico's 3V3(OUT) pin (physical
  pin 36) — the coil driver needs a full 5V even though IN itself is fine
  at 3.3V logic.
- Pico GND, relay logic GND, and relay DC- (if not truly opto-isolated)
  must all share a common reference.

## Bench test order
1. Power Pico by USB
2. Power relay board from 5V
3. Tie Pico GND to relay GND
4. Confirm GP15 toggles relay
5. Wire DS3231 to GP0/GP1 and confirm time reads
6. Set RTC using `set_rtc_once.py`
7. Only then connect the 24VAC valve wiring

## Relay test
- Boot device
- Open `/start`
- Listen for relay click
- Open `/stop`
- Confirm relay releases
- If reversed, set `"relay_active_high": false`

## Valve test
- AC1 -> relay COM
- relay NO -> valve control wire
- AC2 -> valve common wire
- Open `/start`
- Confirm water path opens
- Open `/stop`
- Confirm valve closes
