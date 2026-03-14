# Pico W Sprinkler Controller – Ready-to-Run Starter

This project is a working single-zone MicroPython sprinkler controller for:

- Raspberry Pi Pico W
- DS3231 RTC
- 5V relay module
- 24VAC Rain Bird valve

## Pin mapping
- Relay IN -> GP15
- Relay GND -> Pico GND
- Relay VCC -> 5V external supply
- DS3231 SDA -> GP0
- DS3231 SCL -> GP1
- DS3231 VCC -> 3V3
- DS3231 GND -> Pico GND

## Valve wiring
- 24VAC AC1 -> Relay COM
- Relay NO -> Valve control wire
- 24VAC AC2 -> Valve common wire

## Files to edit first
- `secrets.py`
- `config.json`

## Bring-up order
1. Copy files to Pico
2. Edit Wi-Fi in `secrets.py`
3. Boot Pico
4. Visit the IP printed in serial console
5. Test `/start` and `/stop`
6. Set RTC using `set_rtc_once.py`
7. Configure schedule in browser

## Important
If the relay behaves backwards, set:

```json
"relay_active_high": false
```

in `config.json`
