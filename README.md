# LetItRain v1.1.0
**Raspberry Pi Pico W sprinkler controller with iOS app control**

## Architecture

| Mode   | How it works |
|--------|-------------|
| **Local** | iOS app ↔ Pico HTTP API directly over Wi-Fi. Full control. |
| **Remote** | iOS app reads Firebase status (read-only). Can skip today's run. |

The Pico only ever **writes** to Firebase (status heartbeat every 15s, local IP on boot). It reads only the `overrides` node to check for skip signals. Firebase is never in the command path for relay control.

---

## Firebase Setup (Required Before First Use)

Complete these steps in the Firebase Console **before** flashing the Pico or building the iOS app.

### 1. Create Project
- https://console.firebase.google.com → Add project → `LetItRain`
- Disable Google Analytics

### 2. Enable Realtime Database
- Build → Realtime Database → Create Database → `us-central1` → Locked mode

### 3. Set Security Rules
In Realtime Database → Rules, paste the following.  
**Replace `PICO_UID_HERE`** with the UID of the Pico device account (created in step 5):

```json
{
  "rules": {
    "devices": {
      "$device_id": {
        "meta": {
          ".read": "auth != null",
          ".write": "auth != null && auth.uid === 'PICO_UID_HERE'"
        },
        "status": {
          ".read": "auth != null",
          ".write": "auth != null && auth.uid === 'PICO_UID_HERE'"
        },
        "overrides": {
          ".read": "auth != null && auth.uid === 'PICO_UID_HERE'",
          ".write": "auth != null"
        },
        "zones": {
          ".read": "auth != null",
          ".write": "auth != null"
        },
        "schedule": {
          ".read": "auth != null",
          ".write": "auth != null"
        },
        "update": {
          ".read": "auth != null",
          ".write": "auth != null"
        }
      }
    },
    "users": {
      "$uid": {
        ".read": "auth != null && auth.uid === $uid",
        ".write": "auth != null && auth.uid === $uid"
      }
    }
  }
}
```
`zones`/`schedule`/`update` are writable by any signed-in user (not just the Pico) since the app needs to push schedule edits and update-check requests for the Pico to pick up — the Pico is the only writer for `meta`/`status` (device-reported facts), and the only writer for `overrides` reads (skip-day requests still come from the app).

### 4. Enable Authentication
- Build → Authentication → Get started → Email/Password → Enable

### 5. Create Two User Accounts
In Authentication → Users → Add user:

**Your personal account** (for the iOS app):
- Email: your real email address
- Password: strong password you'll remember
- Note the UID shown in the Users table

**Pico device account**:
- Email: `pico-device@letitrain.local`
- Password: generate a random 40-character string (use a password manager)
- Note the UID → replace `PICO_UID_HERE` in the security rules above
- **Keep the password somewhere safe** — you'll need it for `secrets.py`

### 6. Collect Credentials
You'll need these in the next steps:
- **Web API Key**: Project Settings → General → Your apps → Web API Key
- **Database URL**: Realtime Database panel → the URL at the top (e.g. `https://letitrain-default-rtdb.firebaseio.com`)
- **Pico device email**: `pico-device@letitrain.local`
- **Pico device password**: the 40-char string from step 5

### 7. Register iOS App
- Project Settings → Your apps → Add app → iOS
- Bundle ID: `com.yourname.letitrain` (match what you'll use in Xcode)
- Download `GoogleService-Info.plist` → add to Xcode project

### 8. Initialize Database Schema
In Realtime Database → Data, manually create this structure (or let the Pico write it on first boot):

```
devices/
  pico-zone-1/
    meta/
      local_ip: "0.0.0.0"
      firmware_version: "1.1.0"
      device_name: "Pico Sprinkler Controller"
    status/
      is_running: false
      current_mode: "idle"
      device_online: false
      last_heartbeat: 0
      active_skip: false
    overrides/
      skip_today: false
```

---

## Pico W Setup

### 1. Fill in secrets.py
Edit `secrets.py` and replace every `REPLACE_ME` value:

```
WIFI_SSID       = "your home Wi-Fi name"
WIFI_PASSWORD   = "your Wi-Fi password"
FIREBASE_API_KEY    = "AIzaSy..."       ← Web API Key from Firebase
FIREBASE_EMAIL      = "pico-device@letitrain.local"
FIREBASE_PASSWORD   = "your-40-char-pico-account-password"
FIREBASE_DB_URL     = "https://letitrain-default-rtdb.firebaseio.com"
FIREBASE_DEVICE_ID  = "pico-zone-1"
FIREBASE_STORAGE_BUCKET = "your-project-id.appspot.com"   ← see OTA Updates section below
UTC_OFFSET_HOURS    = -5   ← your timezone's STANDARD offset from UTC, e.g. -5 for US Eastern, -6 Central, -7 Mountain, -8 Pacific
```

`UTC_OFFSET_HOURS` is used only for matching your schedule's local start times and determining "today" for skip-day — it does not affect Firebase timestamps, which are always true UTC. MicroPython has no timezone/DST database, so this is a fixed manual number: pick standard time (not daylight saving) and expect scheduled runs to drift by an hour during DST, or update the value twice a year if you want to track it exactly.

### 2. Flash Files to Pico
Copy all `.py` files and folders to the Pico (using Thonny or rshell):
```
main.py
secrets.py
version.json
config.json
netcfg/wifi.py
firebase/__init__.py
firebase/client.py
firebase/status_writer.py
firebase/override_reader.py
firebase/schedule_sync.py
web/server.py
core/scheduler.py
core/state.py
core/unix_time.py
hardware/relay.py
hardware/ds3231.py
hardware/status_led.py
storage/config_store.py
update/updater.py
```

### 3. Router — DHCP Reservation (Recommended)
Find the Pico's MAC address (printed in serial output on first boot) and create a DHCP reservation in your router so its IP never changes. Alternatively, the app reads the IP from Firebase on every connection — both approaches work.

### 4. Status LED Wiring

Two indicator LEDs (green + red) show boot/connectivity state without needing a serial console.

| LED   | Pico Pin        | Notes |
|-------|------------------|-------|
| Green | GPIO16 (pin 21) | Boot / running status |
| Red   | GPIO17 (pin 22) | Connectivity / failure status |

Wiring for each LED (standard 5mm indicator LED):
```
GPIO pin ──► 220–330Ω resistor ──► LED anode (long leg)
LED cathode (short leg) ──► GND (any GND pin, e.g. physical pin 18 or 23)
```
GPIO16/17 drive HIGH = 3.3V, which is within spec for a standard LED + resistor — no transistor needed. Do not skip the resistor; driving an LED directly off a GPIO pin with no resistor can damage the pin.

**Behavior:**
| State | Green | Red |
|-------|-------|-----|
| Booting (Wi-Fi/Firebase connecting) | flash 3s on / 1s off | off |
| Running normally (Firebase reachable) | solid on | off |
| Running, no internet/Firebase | solid on | flash 5s on / 2s off |
| Boot failed (unrecoverable startup error) | off | flash rapidly, 150ms on / 150ms off |

Pin numbers are set in `hardware/status_led.py` → `StatusLED(green_pin=16, red_pin=17)` in `main.py` — change both if you wire to different GPIOs. GPIO16/17 were picked because they're free: I2C uses GPIO0/1, and zone relays use GPIO11–15.

### 5. Verify
Open a serial terminal (Thonny works). You should see:
```
LetItRain v1.1.0 booting...
Connecting to Wi-Fi: YourSSID
Wi-Fi connected on attempt N
Firebase: authenticated OK
Firebase: meta/local_ip pushed: 192.168.x.x
HTTP server listening on port 80
Main loop started.
```

---

## OTA Updates (via Firebase Cloud Storage)

The Pico checks for a new firmware version on every boot and every 6 hours while running, over the internet — it does **not** need to be on the same Wi-Fi network as the machine that published the update. If a newer version is found, it downloads the files listed in the manifest and reboots into them as soon as no zone is actively running (never mid-cycle).

### One-time setup
1. Firebase Console → **Build → Storage** → get started (default bucket is fine).
2. Rules tab → publish:
   ```
   rules_version = '2';
   service firebase.storage {
     match /b/{bucket}/o {
       match /ota/{allPaths=**} {
         allow read: if request.auth != null;
         allow write: if false;   // uploads only via Console/gsutil, never from a client
       }
     }
   }
   ```
3. Copy the bucket name shown at the top of the Storage panel (e.g. `letitrain-75815.appspot.com`) into `secrets.py`'s `FIREBASE_STORAGE_BUCKET`.

### Publishing an update
1. Bump the version in `version.json`.
2. Upload the changed files to Storage under `ota/{version}/{same relative path as on-device}` — e.g. `ota/1.3.0/main.py`, `ota/1.3.0/hardware/status_led.py`.
3. Upload/overwrite `ota/manifest.json`:
   ```json
   {
     "version": "1.3.0",
     "files": [
       {"path": "main.py"},
       {"path": "hardware/status_led.py"}
     ]
   }
   ```
   Only list files that changed — `check_for_update()` in `update/updater.py` overwrites exactly what's listed, nothing else.
4. Every Pico polling that bucket picks it up within `UPDATE_CHECK_INTERVAL` (6 hours), immediately on its next boot, or immediately if triggered manually from the app (below).

Check `update_status.json` on the device (via Thonny), or `devices/{id}/update` in Firebase, for the current state (`idle` / `checking` / `downloading` / `staged` / `error`) if an update doesn't seem to be landing.

### Manual "check now" from the app
The Dashboard's Device Info card has a "Check for Update" button — it writes `devices/{id}/update/requested = true`. The Pico checks that flag every 15s (the same cadence as its status heartbeat), clears it immediately so it only fires once, and runs `check_for_update()` right away instead of waiting for the 6-hour timer. Current status/progress is pushed to the same `update` node every 15s so the app can show it live.

---

## iOS App Setup
See `ios/README.md` for Xcode setup, Firebase SDK, and App Store submission steps.

---

## Firebase Cloud Functions (Push Notifications)

```bash
cd cloud_functions
npm install
firebase login
firebase use --add    # select LetItRain project
firebase deploy --only functions
```

After deploying, find your user UID (Firebase Console → Authentication → Users) and set it:
```bash
firebase functions:config:set app.user_uid="YOUR_UID_HERE"
```

---

## Future: IFTTT Rain Skip (v1.2)
See `cloud_functions/ifttt_rain_hook.js` for full implementation documentation.  
The database schema and Pico firmware already support this — it's ready to be wired up.

---

## File Structure

```
LetItRain/
├── main.py                    ← Pico entry point (rewritten v1.1)
├── secrets.py                 ← Wi-Fi + Firebase credentials (fill in before flash)
├── config.json                ← Device config (persisted on Pico flash)
├── version.json               ← 1.1.0
├── netcfg/wifi.py            ← Wi-Fi connection helper
├── firebase/
│   ├── client.py              ← Firebase REST client (MicroPython)
│   ├── status_writer.py       ← Writes status/meta to Firebase
│   └── override_reader.py     ← Reads skip-today overrides from Firebase
├── web/server.py              ← Local HTTP JSON API (trimmed, no HTML UI)
├── core/                      ← Scheduler + state (unchanged)
├── hardware/                  ← Relay + DS3231 (unchanged)
├── storage/                   ← Config persistence (unchanged)
├── cloud_functions/           ← Firebase Cloud Functions (Node.js)
│   ├── index.js               ← Push notifications on run start/stop
│   └── ifttt_rain_hook.js     ← STUB: IFTTT rain integration (v1.2)
└── ios/                       ← iOS SwiftUI app source
    ├── README.md              ← Xcode setup instructions
    └── LetItRain/
        ├── LetItRainApp.swift
        ├── Managers/ConnectionManager.swift
        ├── ViewModels/
        ├── Networking/
        ├── Models/
        └── Views/
```
