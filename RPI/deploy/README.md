# Deploying to the Raspberry Pi 3 A+

One-time setup for a fresh Raspberry Pi OS Lite (64-bit) install.

## 1. Enable I2C and the hardware watchdog

Edit `/boot/firmware/config.txt` (or `/boot/config.txt` on older images) and add:

```
dtparam=i2c_arm=on
dtparam=watchdog=on
```

Enable systemd's use of the hardware watchdog by adding to
`/etc/systemd/system.conf`:

```
RuntimeWatchdogSec=30
```

Reboot for both to take effect. Confirm with:

```
ls /dev/i2c-1 /dev/watchdog
```

## 2. Install the app

```
sudo mkdir -p /opt/letitrain
sudo chown $USER /opt/letitrain
git clone --branch feature/MajorFirmwareUpgrade_Alpha-2-0-0 <repo-url> /opt/letitrain
cd /opt/letitrain/RPI
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

The clone pulls down the whole monorepo (this `RPI/` folder plus `ios/`
and the shared Firebase Cloud Functions) -- everything below happens
inside `RPI/`.

## 3. Per-device secrets and config

`device_secrets.py` is gitignored and per-device (like the old Pico
`secrets.py`) -- it does not come from the clone. Create it at
`/opt/letitrain/RPI/device_secrets.py` with this device's own
`FIREBASE_DEVICE_ID` (must be unique across every device sharing the
Firebase project -- see the root README's multi-tenant notes).

Check `config.json`'s `zones[].pin` values and the LCD pin assignment in
`main.py`'s boot sequence (`dat_pin`/`clk_pin`/`lat_pin`) against your
actual wiring before first boot -- `main.py` carries forward the Pico
build's `dat_pin=11, lat_pin=11` values as-is, which look like a
pre-existing bug (both wired to the same GPIO). Confirm the real shift
register wiring and fix the pin numbers here if so.

## 4. Install the systemd unit

```
sudo cp /opt/letitrain/RPI/deploy/letitrain.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now letitrain
```

## 5. Verify

```
journalctl -u letitrain -f
curl http://localhost/status
```

Confirm the watchdog actually recovers a hang before relying on it:

```
sudo systemctl kill -s SIGSTOP letitrain   # freeze the process
# wait > WatchdogSec -- systemd should restart the unit automatically
journalctl -u letitrain --since "2 min ago"
```
