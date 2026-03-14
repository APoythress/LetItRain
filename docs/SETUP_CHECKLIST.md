# Setup Checklist

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
