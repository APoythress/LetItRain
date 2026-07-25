# LetItRain v1.1.0
**Raspberry Pi Pico W sprinkler controller with iOS app control**

## Architecture

| Mode   | How it works |
|--------|-------------|
| **Local** | iOS app ↔ Pico HTTP API directly over Wi-Fi. Full control. |
| **Remote** | iOS app reads Firebase status (read-only). Can skip today's run. |

The Pico only ever **writes** to Firebase (status heartbeat every 30s, local IP on boot). It reads only the `overrides` node to check for skip signals. Firebase is never in the command path for relay control.

**Safety net:** a hardware watchdog (`machine.WDT`, 8s timeout) is armed once boot completes. It's fed after each network operation in the main loop and every 100ms while idle — if the loop ever stops reaching those points for 8 seconds (a hang of any kind, regardless of cause), the board hard-resets. `relay.all_off()` unconditionally runs first on every boot, so a stuck-open zone always gets shut off within seconds even if the software issue that caused the hang is never diagnosed.

---

## Firebase Setup (Required Before First Use)

Complete these steps in the Firebase Console **before** flashing the Pico or building the iOS app.

### 1. Create Project
- https://console.firebase.google.com → Add project → `LetItRain`
- Disable Google Analytics

### 2. Enable Realtime Database
- Build → Realtime Database → Create Database → `us-central1` → Locked mode

### 3. Set Security Rules
In Realtime Database → Rules, paste the following as-is — **no UID needs to be hand-edited into this text**, for one project or for twenty. Ownership of each `device_id` node is established dynamically instead of hardcoded:

```json
{
  "rules": {
    "devices": {
      "$device_id": {
        "device_owner_uid": {
          ".read": "auth != null",
          ".write": "auth != null && (!data.exists() || data.val() === auth.uid)"
        },
        "meta": {
          ".read": "auth != null",
          ".write": "auth != null && auth.uid === root.child('devices').child($device_id).child('device_owner_uid').val()"
        },
        "status": {
          ".read": "auth != null",
          ".write": "auth != null && auth.uid === root.child('devices').child($device_id).child('device_owner_uid').val()"
        },
        "overrides": {
          ".read": "auth != null && auth.uid === root.child('devices').child($device_id).child('device_owner_uid').val()",
          ".write": "auth != null && root.child('users').child(auth.uid).child('device_id').val() === $device_id"
        },
        "zones": {
          ".read": "auth != null && (auth.uid === root.child('devices').child($device_id).child('device_owner_uid').val() || root.child('users').child(auth.uid).child('device_id').val() === $device_id)",
          ".write": "auth != null && root.child('users').child(auth.uid).child('device_id').val() === $device_id"
        },
        "schedule": {
          ".read": "auth != null && (auth.uid === root.child('devices').child($device_id).child('device_owner_uid').val() || root.child('users').child(auth.uid).child('device_id').val() === $device_id)",
          ".write": "auth != null && root.child('users').child(auth.uid).child('device_id').val() === $device_id"
        },
        "update": {
          ".read": "auth != null && (auth.uid === root.child('devices').child($device_id).child('device_owner_uid').val() || root.child('users').child(auth.uid).child('device_id').val() === $device_id)",
          ".write": "auth != null && (auth.uid === root.child('devices').child($device_id).child('device_owner_uid').val() || root.child('users').child(auth.uid).child('device_id').val() === $device_id)"
        }
      }
    },
    "users": {
      "$uid": {
        ".read": "auth != null && auth.uid === $uid",
        "device_id": { ".write": false },
        "fcm_token": { ".write": "auth != null && auth.uid === $uid" }
      }
    }
  }
}
```

Two different ownership mechanisms, deliberately:
- **`device_owner_uid`** (gates `meta`/`status`) is **self-claimed**: whichever account first authenticates and writes there becomes its permanent owner. Safe because only the one physical Pico that holds that device account's credentials (in its own `secrets.py`) will ever attempt that write — this is what removes the old "look up your Pico's UID and hand-paste it into the rules" step entirely. Two Picos left on the same default `FIREBASE_DEVICE_ID` will race for this; whichever loses gets a clear, specific rejection at boot rather than a confusing generic one (see `main.py`'s device_owner_uid claim step).
- **`users/{uid}/device_id`** (gates `zones`/`schedule`/`overrides`/`update` — i.e. app control) is **admin-assigned only** (`.write: false` — set it from the Console's Data tab, never from the app). This is intentionally *not* self-claimable: in a shared project, letting a signed-in user write their own `users/{uid}/device_id` would let them grant themselves control of anyone else's device just by writing that field. See "Onboarding a new device" below for the exact steps.

### 4. Enable Authentication
- Build → Authentication → Get started → Email/Password → Enable

### 5. Create Two User Accounts
In Authentication → Users → Add user:

**Your personal account** (for the iOS app):
- Email: your real email address
- Password: strong password you'll remember
- Note the UID shown in the Users table — you'll assign it to your own device in step 9 below

**Pico device account**:
- Email: `pico-device@letitrain.local`
- Password: generate a random 40-character string (use a password manager)
- No UID copying needed here — the security rules above let this account self-claim ownership of its device_id automatically on first boot
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

### 9. Onboarding a new device (yourself first, then any friends)

Whether it's your own first device or a friend's, the steps are the same — this project supports many people sharing one Firebase project, each cryptographically confined to their own `device_id`:

1. **Create two Firebase Auth accounts** for this person (Authentication → Users → Add user), same pattern as step 5: a personal account (for their iOS app) and a device account (for their Pico). Give them the device account's email/password and a device password to keep private.
2. **Pick a `FIREBASE_DEVICE_ID`** unique across everyone sharing this project (e.g. `west-home`, `friend-name-backyard`) and give it to them to put in their `secrets.py`, alongside their device account's email/password.
3. Have them **flash their Pico and boot it once**. The device account self-claims `devices/{their_device_id}/device_owner_uid` automatically — nothing to copy or paste for this part.
4. Have them **sign into the iOS app once** with their personal account (this creates their Firebase Auth user session, giving you their UID to reference).
5. In Realtime Database → Data, **manually set `users/{their_personal_uid}/device_id = "{their_device_id}"`**. This is the one step that must be done from the Console — the rules deliberately don't allow the app to write this field itself (see the security rules note above), since that's what stops one person from granting themselves access to someone else's device.

After step 5, their app shows only their own device's status/schedule, and their Pico only ever reads/writes its own node — cross-device access is rejected by the rules regardless of what either side's code does.

### 1. Fill in secrets.py
Edit `secrets.py` and replace every `REPLACE_ME` value:

```
WIFI_SSID       = "your home Wi-Fi name"
WIFI_PASSWORD   = "your Wi-Fi password"
FIREBASE_API_KEY    = "AIzaSy..."       ← Web API Key from Firebase
FIREBASE_EMAIL      = "pico-device@letitrain.local"
FIREBASE_PASSWORD   = "your-40-char-pico-account-password"
FIREBASE_DB_URL     = "https://letitrain-default-rtdb.firebaseio.com"
FIREBASE_DEVICE_ID  = "pico-zone-1"   ← must be unique across everyone sharing this Firebase project, see "Onboarding a new device" above
FIREBASE_STORAGE_BUCKET = "your-project-id.appspot.com"   ← see OTA Updates section below
UTC_OFFSET_HOURS    = -5   ← your timezone's STANDARD offset from UTC, e.g. -5 for US Eastern, -6 Central, -7 Mountain, -8 Pacific
# FIREBASE_EXPECTED_UID = "..."   ← optional, leave commented out on first boot; see below
```

`UTC_OFFSET_HOURS` is used only for matching your schedule's local start times and determining "today" for skip-day — it does not affect Firebase timestamps, which are always true UTC. MicroPython has no timezone/DST database, so this is a fixed manual number: pick standard time (not daylight saving) and expect scheduled runs to drift by an hour during DST, or update the value twice a year if you want to track it exactly.

`FIREBASE_EXPECTED_UID` is an optional cross-check, not something you fill in up front: after this device's first successful boot ("Firebase: authenticated OK" in the serial console), find its UID in Firebase Console → Authentication → Users and paste it in. Every later boot then loudly warns if the credentials above ever end up on the wrong physical board (e.g. a friend's `secrets.py` copied onto this one by mistake) instead of failing silently/confusingly via a rejected write several steps later.

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
core/mem_diag.py
hardware/relay.py
hardware/ds3231.py
hardware/status_led.py
hardware/lcd1602.py
hardware/lcd_status.py
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

### 5. 16x2 LCD Wiring (optional)

A 16x2 character LCD on an [Adafruit Character LCD Backpack](https://www.adafruit.com/product/292) in its SPI/shift-register mode shows live status without a serial console. This backpack exposes 5 pins — LAT, DAT, CLK, 3-5V, GND — driving the LCD through an onboard 74HC595 shift register rather than I2C.

| Backpack Pin | Pico Pin |
|--------------|----------|
| LAT | GPIO20 |
| DAT | GPIO19 |
| CLK | GPIO18 |
| 3-5V | 3V3 (physical pin 36) |
| GND | any GND pin |

Pin numbers are set in `hardware/lcd1602.py`'s instantiation in `main.py` — `LCD1602(dat_pin=18, clk_pin=19, lat_pin=20)` — change if you wire to different GPIOs. GPIO18–20 were picked because they're free alongside the status LEDs (16/17) and relays (11–15).

**Layout** (updates automatically, redrawing only the fields that changed):
```
Zone 3      Tue 05:00
1.100        v1.2.16
```
Top-left: active zone, or "Idle". Top-right: next scheduled run. Bottom-left: local IP (shortened to its last two octets if the full address plus the version won't both fit). Bottom-right: firmware version.

The display is optional — if unwired or faulty, `main.py` logs it and continues without one; nothing else on the controller depends on it.

### 6. Verify
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
     ],
     "deletes": [
       "hardware/old_module.py"
     ]
   }
   ```
   Only list files that changed — `check_for_update()` in `update/updater.py` overwrites exactly what's listed, nothing else. There is no way to signal a deletion by omission: `files` can only add or overwrite, since there's nothing in Storage to download for a file that should stop existing. If a release removes a file from the repo, add its path to `deletes` (optional key) so devices that already have it get it removed; `os.remove()` failing because it's already absent is treated as success.
4. Every Pico polling that bucket picks it up within `UPDATE_CHECK_INTERVAL` (6 hours), immediately on its next boot, or immediately if triggered manually from the app (below).

Check `update_status.json` on the device (via Thonny), or `devices/{id}/update` in Firebase, for the current state (`idle` / `checking` / `downloading` / `staged` / `error`) if an update doesn't seem to be landing.

### Manual "check now" from the app
The Dashboard's Device Info card has a "Check for Update" button — it writes `devices/{id}/update/requested = true`. The Pico checks that flag every 45s, clears it immediately so it only fires once, and runs `check_for_update()` right away instead of waiting for the 6-hour timer. Current status/progress is pushed to the same `update` node every 45s so the app can show it live.

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
