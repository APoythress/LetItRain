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
        "status": {
          ".read": "auth != null",
          ".write": "auth != null && auth.uid === 'PICO_UID_HERE'"
        },
        "overrides": {
          ".read": "auth != null && auth.uid === 'PICO_UID_HERE'",
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
```

### 2. Flash Files to Pico
Copy all `.py` files and folders to the Pico (using Thonny or rshell):
```
main.py
secrets.py
version.json
config.json
network/wifi.py
firebase/__init__.py
firebase/client.py
firebase/status_writer.py
firebase/override_reader.py
web/server.py
core/scheduler.py
core/state.py
hardware/relay.py
hardware/ds3231.py
storage/config_store.py
```

### 3. Router — DHCP Reservation (Recommended)
Find the Pico's MAC address (printed in serial output on first boot) and create a DHCP reservation in your router so its IP never changes. Alternatively, the app reads the IP from Firebase on every connection — both approaches work.

### 4. Verify
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
├── network/wifi.py            ← Wi-Fi connection helper
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
