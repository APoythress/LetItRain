# Deploying to the Raspberry Pi 3 A+

One-time setup for a fresh Raspberry Pi OS Lite (64-bit) install.

## 1. Enable I2C and the hardware watchdog

SSH in, then run:

```bash
echo -e "\ndtparam=i2c_arm=on\ndtparam=watchdog=on" | sudo tee -a /boot/firmware/config.txt
```

(If `/boot/firmware/config.txt` doesn't exist on your image, use
`/boot/config.txt` instead in every command in this section.)

The LCD backpack's MCP23008 talks I2C over the same DAT/CLK terminal-block
pins its SPI mode would otherwise use, via a second, software (bit-banged)
I2C bus rather than the Pi's dedicated hardware I2C1 (which the DS3231 RTC
uses instead, on GPIO2/GPIO3). Add this too, adjusting the GPIO numbers if
your DAT/CLK wiring differs from `main.py`'s (currently GPIO27/GPIO17):

```bash
echo "dtoverlay=i2c-gpio,bus=3,i2c_gpio_sda=27,i2c_gpio_scl=17" | sudo tee -a /boot/firmware/config.txt
```

Enable systemd's use of the hardware watchdog:

```bash
echo "RuntimeWatchdogSec=30" | sudo tee -a /etc/systemd/system.conf
```

Reboot for all three to take effect:

```bash
sudo reboot
```

Wait ~30-60s, then reconnect (`ssh <username>@<hostname>.local`) and confirm:

```bash
ls /dev/i2c-1 /dev/i2c-3 /dev/watchdog
sudo apt update && sudo apt install -y i2c-tools   # not installed by default on Lite images
i2cdetect -y 3   # should show 0x20 -- the LCD backpack's MCP23008
```

If `/dev/i2c-1` is missing, run `sudo raspi-config nonint do_i2c 0` and
reboot again — the manual `dtparam=i2c_arm=on` line alone doesn't always
load the `i2c-dev` kernel module on every image; `raspi-config` handles
both the device-tree flag and the module together.

## 2. Install the app

Neither `git` nor `python3-venv` are guaranteed to be preinstalled on a
fresh Lite image:

```bash
sudo apt update && sudo apt install -y git python3-venv python3-pip
```

```bash
sudo mkdir -p /opt/letitrain
sudo chown $USER /opt/letitrain
git clone --branch main <repo-url> /opt/letitrain
cd /opt/letitrain/RPI
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

The clone pulls down the whole monorepo (this `RPI/` folder plus `ios/`
and the shared Firebase Cloud Functions) -- everything below happens
inside `RPI/`.

The repo is now owned by your regular user, but `letitrain.service` runs
as root (see step 4) — `git` refuses to operate on a repo across that
ownership boundary unless told it's safe. Required once per device, or the
OTA update mechanism (see root README) will fail every time it tries to
apply an update:

```bash
sudo git config --global --add safe.directory /opt/letitrain
```

## 3. Per-device secrets and config

`device_secrets.py` is gitignored and per-device -- it does not come from
the clone. Create it with placeholder values, then fill them in:

```bash
cat > /opt/letitrain/RPI/device_secrets.py << 'EOF'
FIREBASE_API_KEY        = "REPLACE_ME"   # Web API Key -- Firebase Console -> Project Settings -> General
FIREBASE_EMAIL          = "REPLACE_ME"   # this device's account email, e.g. device-name@letitrain.local
FIREBASE_PASSWORD       = "REPLACE_ME"   # this device's account password
FIREBASE_DB_URL         = "REPLACE_ME"   # e.g. https://your-project-default-rtdb.firebaseio.com
FIREBASE_DEVICE_ID      = "REPLACE_ME"   # must be unique across every device sharing the project -- see root README
FIREBASE_STORAGE_BUCKET = "REPLACE_ME"   # e.g. your-project-id.appspot.com
EOF

nano /opt/letitrain/RPI/device_secrets.py
```

(In `nano`: edit the `REPLACE_ME` values, then `Ctrl+O`, `Enter`, `Ctrl+X`
to save and exit.)

If you already have a working `device_secrets.py` from another device on
this same Firebase project, it's faster to `scp` it over from that machine
and just change `FIREBASE_EMAIL`/`FIREBASE_PASSWORD`/`FIREBASE_DEVICE_ID`
to this device's own values rather than retyping everything — but every
field must actually be unique to this device; copying it unchanged makes
two devices fight over the same identity (see root README's onboarding
section).

Check `config.json`'s `zones[].pin` values and the LCD/status LED pin
assignments in `main.py`'s boot sequence against your actual wiring before
first boot -- see **`RPI/hardware/GPIO_PINOUT.md`** for the full reference
wiring (including the LCD backpack's I2C-mode gotcha) and update both the
code and that doc together if you wire to different GPIOs.

```bash
cat /opt/letitrain/RPI/config.json | python3 -m json.tool   # view current zone pins
nano /opt/letitrain/RPI/config.json                          # edit if they don't match your wiring
```

## 3a. Switching WiFi networks (e.g. testing here, deploying elsewhere)

Raspberry Pi OS uses NetworkManager, which can hold multiple saved WiFi
profiles at once and will connect to whichever is actually in range --
useful for building/testing a unit on your own network before it goes to
its final location. Add the destination network as a second profile
without touching the existing one:

```bash
sudo nmcli connection add type wifi ifname wlan0 con-name "destination-wifi" \
  ssid "SSID" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "PASSWORD"
```

`nmcli connection show` lists all saved profiles; `sudo nmtui` is a
menu-driven alternative if you'd rather not type `nmcli` by hand. Since the
Pi 3 A+ has no Ethernet port, get the destination network's credentials
staged *before* moving the device there -- otherwise there's no fallback
way to reach it to fix networking on-site.

## 4. Install the systemd unit

```bash
sudo cp /opt/letitrain/RPI/deploy/letitrain.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now letitrain
```

## 5. Verify

```bash
journalctl -u letitrain -f
curl http://localhost/status
```

Confirm the watchdog actually recovers a hang before relying on it:

```bash
sudo systemctl kill -s SIGSTOP letitrain   # freeze the process
# wait > WatchdogSec -- systemd should restart the unit automatically
journalctl -u letitrain --since "2 min ago"
```
