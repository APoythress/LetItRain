# LetItRain v2.0.0-alpha
**Raspberry Pi 3 A+ sprinkler controller with iOS app control**

This supersedes the earlier Raspberry Pi Pico W build — the device is now a
full Linux box (Raspberry Pi OS Lite, 64-bit) running CPython under
`systemd`, not MicroPython. See `RPI/` for the device firmware/software,
`RPI/deploy/README.md` for first-boot setup, and
`RPI/hardware/GPIO_PINOUT.md` for wiring a new physical unit end to end.

## Architecture

| Mode   | How it works |
|--------|-------------|
| **Local** | iOS app ↔ Pi's local FastAPI server directly over Wi-Fi. Full control — manual start/stop, schedule/zone editing, instant update checks. |
| **Remote** | iOS app reads Firebase status (read-only) — last run time/zone/status, and when the device last synced. Remote writes available: "skip the schedule for N days" (out-of-town use case), and confirming an already-detected software update. |

The iOS app is **local-only for schedule/zone editing and manual start/stop**
— both require being on the same Wi-Fi as the Pi. This isn't just a UI
restriction: the Firebase security rules (below) reject a `zones`/`schedule`
write from the app regardless of what the client attempts.

Unlike the old Pico build's single batched 15-minute Firebase sync pass
(that batching existed specifically to avoid wedging the Pico W's onboard
WiFi chip under frequent TLS traffic — a full Linux network stack has no
equivalent failure mode), the Pi runs each concern on its own independent
`asyncio` task and cadence:

- Status → Firebase: every 60s
- Zones/schedule/IP → Firebase: every 300s automatically, **and immediately**
  whenever `/config` actually changes zones or schedule (a save doesn't wait
  for the next periodic cycle)
- RTC mirror (if wired): every hour
- Update check: every 6h, or immediately on a manual "Check Now"/"Update Now"
- Firebase is never in the command path for relay control — schedule
  execution and manual start/stop are entirely local.

The iOS app doesn't poll on a fixed timer either: it fetches status once
when a screen appears, once after any action (start/stop/skip), and once
whenever it detects it's just joined the local network. A running zone's
countdown needs no polling — it's computed client-side from the fetched end
time. Local/remote mode detection re-evaluates on network changes, app
foreground, or a failed request, not a recurring timer, to avoid two
independent timers colliding against the Pi's single-threaded local API.

**Safety net:** `systemd` owns process supervision and a hardware watchdog
(`WatchdogSec=30` in `deploy/letitrain.service`, fed via `sd_notify` every
10s — see `main.py`'s `watchdog_loop()`). If the event loop ever stops
reaching that heartbeat for any reason (a hang of any kind), `systemd`
hard-restarts the service. `relay.all_off()` unconditionally runs first on
every boot, so a stuck-open zone always gets shut off within seconds
regardless of what caused the restart.

---

## Firebase Setup (Required Before First Use)

Complete these steps in the Firebase Console **before** setting up the Pi or
building the iOS app. This section is unchanged from the Pico build — the
schema and security rules carried over as-is.

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
          ".write": "auth != null && auth.uid === root.child('devices').child($device_id).child('device_owner_uid').val()"
        },
        "schedule": {
          ".read": "auth != null && (auth.uid === root.child('devices').child($device_id).child('device_owner_uid').val() || root.child('users').child(auth.uid).child('device_id').val() === $device_id)",
          ".write": "auth != null && auth.uid === root.child('devices').child($device_id).child('device_owner_uid').val()"
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
        "device_id": { ".write": false }
      }
    }
  }
}
```

Two different ownership mechanisms, deliberately:
- **`device_owner_uid`** (gates `meta`/`status`, and `zones`/`schedule` writes) is **self-claimed**: whichever account first authenticates and writes there becomes its permanent owner. Safe because only the one physical device that holds that device account's credentials (in its own `device_secrets.py`) will ever attempt that write — this removes the old "look up your device's UID and hand-paste it into the rules" step entirely. Two devices left on the same default `FIREBASE_DEVICE_ID` will race for this; whichever loses gets a clear, specific rejection at boot (see `main.py`'s `device_owner_uid` claim step). Restricting `zones`/`schedule` writes to this same owner UID (rather than any assigned app user) is what makes "the app is local-only for schedule editing" a security-rules guarantee, not just a UI choice.
- **`users/{uid}/device_id`** (gates read access to `zones`/`schedule`, and read+write of `overrides`/`update` — i.e. remote skip-for-N-days and update confirmation) is **admin-assigned only** (`.write: false` — set it from the Console's Data tab, never from the app). This is intentionally *not* self-claimable: in a shared project, letting a signed-in user write their own `users/{uid}/device_id` would let them grant themselves control of anyone else's device.

### 4. Enable Authentication
- Build → Authentication → Get started → Email/Password → Enable

### 5. Create Two User Accounts
In Authentication → Users → Add user:

**Your personal account** (for the iOS app):
- Email: your real email address
- Password: strong password you'll remember
- Note the UID shown in the Users table — you'll assign it to your own device in step 9 below

**Device account** (one per physical Pi):
- Email: e.g. `device-name@letitrain.local`
- Password: generate a random 40-character string (use a password manager)
- No UID copying needed here — the security rules above let this account self-claim ownership of its device_id automatically on first boot
- **Keep the password somewhere safe** — you'll need it for `device_secrets.py`

### 6. Collect Credentials
You'll need these in the next steps:
- **Web API Key**: Project Settings → General → Your apps → Web API Key
- **Database URL**: Realtime Database panel → the URL at the top (e.g. `https://letitrain-default-rtdb.firebaseio.com`)
- **Storage bucket name**: Build → Storage panel → the bucket name at the top (e.g. `letitrain-75815.appspot.com`) — not currently used by the OTA mechanism (see below), but collected alongside the rest since `device_secrets.py` has a field for it
- **Device account email/password**: from step 5

### 7. Register iOS App
- Project Settings → Your apps → Add app → iOS
- Bundle ID: match what you'll use in Xcode
- Download `GoogleService-Info.plist` → add to Xcode project

### 8. Initialize Database Schema
This gets created automatically by the device on first successful boot —
nothing to do by hand here unless you want to pre-seed it. Shape, for
reference:

```
devices/
  {device_id}/
    device_owner_uid: "<self-claimed on first boot>"
    meta/
      local_ip: "192.168.x.x"
      firmware_version: "2.0.0-alpha"
      device_name: "LetItRain Controller"
    status/
      is_running: false
      current_mode: "idle"
      device_online: false
      last_synced_epoch: 0
      active_skip: false
    zones/
      1: { name: "Front Garden", pin: 5, enabled: true }
      ...
    schedule/
      monday: { enabled: true, slots: [...] }
      ...
    overrides/
      skip_active: false
      skip_until: null
    update/
      status: "idle"
      current_version: "2.0.0-alpha"
      available_version: null
```

### 9. Onboarding a new device (yourself first, then any friends)

Whether it's your own first device or a friend's, the steps are the same — this project supports many people sharing one Firebase project, each cryptographically confined to their own `device_id`:

1. **Create two Firebase Auth accounts** for this person (Authentication → Users → Add user), same pattern as step 5: a personal account (for their iOS app) and a device account (for their Pi). Give them the device account's email/password to put in their own `device_secrets.py`.
2. **Pick a `FIREBASE_DEVICE_ID`** unique across everyone sharing this project (e.g. `west-home`, `friend-name-backyard`) and give it to them, alongside their device account's email/password.
3. Have them **set up their Pi and boot it once** (see `RPI/deploy/README.md`). The device account self-claims `devices/{their_device_id}/device_owner_uid` automatically — nothing to copy or paste for this part.
4. Have them **sign into the iOS app once** with their personal account (this creates their Firebase Auth user session, giving you their UID to reference).
5. In Realtime Database → Data, **manually set `users/{their_personal_uid}/device_id = "{their_device_id}"`**. This is the one step that must be done from the Console — the rules deliberately don't allow the app to write this field itself, since that's what stops one person from granting themselves access to someone else's device.

After step 5, their app shows only their own device's status/schedule, and their Pi only ever reads/writes its own node — cross-device access is rejected by the rules regardless of what either side's code does.

**If the app is stuck showing "Your account isn't assigned to a device yet"** — this is always step 5 above not having been done yet for that account (or done for the wrong UID). This applies to your own first device too, not just friends' — signing into the app does *not* automatically grant it access to anything; someone has to go into the Console and set `users/{your_personal_uid}/device_id` by hand, exactly once. Note this is a **different** field from `devices/{device_id}/device_owner_uid` (which the device sets on itself, automatically) — mixing the two up is easy to do and won't fix this error.

---

## Setting Up a Physical Device

Full first-boot-to-running-service instructions live in
**`RPI/deploy/README.md`** (flashing the SD card, enabling I2C/watchdog,
cloning the repo, installing the systemd service). Full wiring reference —
every GPIO connection, what each pin is for, and the LCD backpack's I2C
mode gotcha — lives in **`RPI/hardware/GPIO_PINOUT.md`**. Both are written
to be followed start to finish without needing to read the source first.

At a high level: clone this repo to `/opt/letitrain` on the Pi, fill in
`RPI/device_secrets.py` (gitignored, per-device — not part of the clone):

```
FIREBASE_API_KEY        = "AIzaSy..."       ← Web API Key from Firebase
FIREBASE_EMAIL          = "device-name@letitrain.local"
FIREBASE_PASSWORD       = "your-40-char-device-account-password"
FIREBASE_DB_URL         = "https://letitrain-default-rtdb.firebaseio.com"
FIREBASE_DEVICE_ID      = "your-unique-device-id"   ← see "Onboarding a new device" above
FIREBASE_STORAGE_BUCKET = "your-project-id.appspot.com"
# FIREBASE_EXPECTED_UID = "..."   ← optional, leave commented out on first boot; see below
```

`FIREBASE_EXPECTED_UID` is an optional cross-check, not something you fill
in up front: after this device's first successful boot
(`journalctl -u letitrain` shows "Firebase: authenticated OK"), find its UID
in Firebase Console → Authentication → Users and paste it in. Every later
boot then loudly warns if these credentials ever end up on the wrong
physical device (e.g. a friend's `device_secrets.py` copied onto this one
by mistake) instead of failing silently/confusingly via a rejected write
several steps later.

Unlike the Pico build, WiFi and NTP are OS-managed (NetworkManager,
`systemd-timesyncd`), not configured in `device_secrets.py` — see
`RPI/deploy/README.md`, including its section on switching a device between
networks (e.g. testing on your own WiFi before deploying to a friend's).

---

## OTA Updates (git tags)

Replaces the old Pico build's Firebase-Storage-manifest downloader entirely
— that mechanism (`update/updater.py` at the repo root) was MicroPython-only
and never applicable once the device became a normal Linux git clone.
Releases are now just git tags (`vX.Y.Z`, or `X.Y.Z`), applied via
`git fetch` + `git checkout` in place.

**No push notifications yet** — the device checks Firebase for the app to
read, and the app shows a badge; there's no APNs/FCM wiring to actively
notify you. See `RPI/firebase/update_checker.py` and `main.py`'s
`update_loop` for the actual mechanism.

- Every 6 hours (or immediately on a manual "Check Now"/"Update Now" tap),
  the device fetches tags from `origin`, compares the highest version-shaped
  tag to its own `FIRMWARE_VERSION`, and writes the result to
  `devices/{id}/update` in Firebase.
- The iOS Dashboard shows an amber badge + the available version when one's
  found, with an "Update Now" button. Tapping it writes
  `update/apply_requested: true` — works in both local and remote mode,
  since the security rules already allow the assigned app user to write
  this node.
- The device applies the update (`git fetch` + `checkout <tag>`) the next
  time it polls and sees that flag, **deferring instead of interrupting** if
  a zone happens to be running at that moment. A successful checkout ends
  the process; `systemd`'s `Restart=always` relaunches it running the newly
  checked-out code.

**Two operational prerequisites**, not yet automated:
1. `git` refuses to operate across a UID mismatch between the repo owner and
   the user running it (the systemd service runs as root; the repo is
   typically cloned as your regular user) — run once per device:
   ```
   sudo git config --global --add safe.directory /opt/letitrain
   ```
2. `RPI/config.json` is both tracked in git *and* the live file the running
   service mutates constantly (zone names, schedules, etc.) — `git checkout`
   will refuse to run while it has uncommitted changes, which it always
   will in normal operation. This currently blocks every real apply attempt
   until resolved (e.g. by gitignoring `config.json` in favor of a shipped
   template, similar to `device_secrets.py`) — not yet done as of this
   writing.

Publishing a release: bump whatever needs bumping, commit, then
`git tag vX.Y.Z && git push --tags`. Devices pick it up on their next poll.

---

## Clock Sync

The system clock is kept correct primarily by `systemd-timesyncd` (NTP)
once the device has network access — no code here manages that directly.
The DS3231 RTC, if wired, is optional (see `RPI/hardware/GPIO_PINOUT.md`
for why): it seeds the system clock at boot only if the clock looks
obviously wrong (before year 2020 — a sign `fake-hwclock`'s snapshot and
NTP both haven't run yet), and is mirrored from the OS-synced clock once an
hour afterward to correct for its own crystal drift over long uptimes.

**Manual resync**: the Dashboard's Device Info card has a "Resync Time"
button, local mode only — posts directly to the device's
`POST /resync-time` endpoint. Not offered remotely since there's no daily
automatic job depending on it the way the old Pico build had.

---

## Boot Diagnostics

Every boot writes `boot_log.json` next to `main.py`, readable via
`GET /boot-log` on the local network (e.g. `http://<device-ip>/boot-log`
from a browser, or `curl`) — no SSH session or physical access required.

Fields: `firmware_version`, `zones_configured`, `lcd_present`, `rtc_present`,
`local_ip`, `network_reachable`, `firebase_auth_ok`, `firebase_auth_error`,
`firebase_uid`, `expected_uid_mismatch`, `device_owner_uid_claimed`
(`true`/`false`/`null` if never attempted because auth failed).

If the endpoint 404s with "no boot log available yet," the device hasn't
booted since this feature was added — restart the service once.

---

## iOS App Setup
See `ios/README.md` for Xcode setup, Firebase SDK, and App Store submission steps.

---

## Future: IFTTT Rain Skip
See `cloud_functions/ifttt_rain_hook.js` for full implementation documentation.
The database schema and device firmware already support this — it's ready to be wired up.

---

## File Structure

```
LetItRain/
├── README.md                      ← this file
├── manifest.json                  ← legacy: old Pico Storage-manifest OTA scheme, superseded by git-tag updates above
├── update/updater.py              ← legacy: Pico-only OTA downloader (ujson/urequests), not used by RPI/
├── docs/SETUP_CHECKLIST.md        ← legacy: Pico 2 relay wiring, superseded by RPI/hardware/GPIO_PINOUT.md
├── RPI/                           ← current device firmware/software (Raspberry Pi 3 A+, CPython)
│   ├── main.py                    ← entry point — boot sequence + all background tasks
│   ├── device_secrets.py          ← gitignored, per-device Firebase credentials (see setup above)
│   ├── config.json                ← device config: zones, schedule, timezone (see OTA section's caveat)
│   ├── version.json
│   ├── requirements.txt
│   ├── deploy/
│   │   ├── README.md              ← full first-boot setup sequence
│   │   └── letitrain.service      ← systemd unit
│   ├── hardware/
│   │   ├── GPIO_PINOUT.md         ← wiring reference for a new physical build
│   │   ├── relay.py               ← multi-zone relay control (gpiozero)
│   │   ├── status_led.py          ← boot/connectivity indicator LEDs
│   │   ├── lcd1602.py             ← 16x2 LCD driver (I2C/MCP23008 — see GPIO_PINOUT.md)
│   │   ├── lcd_status.py          ← LCD content composition
│   │   └── ds3231.py              ← optional RTC driver (I2C1)
│   ├── firebase/
│   │   ├── client.py              ← Firebase REST client (httpx/asyncio)
│   │   ├── status_writer.py       ← status/meta pushes
│   │   ├── override_reader.py     ← skip-override reads
│   │   ├── schedule_sync.py       ← zones/schedule push (immediate-on-save + periodic)
│   │   └── update_checker.py      ← git-tag OTA detection/application
│   ├── web/server.py              ← local FastAPI JSON API
│   ├── core/                      ← scheduler, controller state, time helpers
│   └── storage/config_store.py    ← config.json persistence
├── ios/                            ← iOS SwiftUI app source
│   ├── README.md                  ← Xcode setup instructions
│   └── LetItRain.iOS/
│       ├── LetItRainApp.swift
│       ├── Managers/ConnectionManager.swift
│       ├── ViewModels/
│       ├── Networking/
│       ├── Models/
│       └── Views/
└── cloud_functions/                ← Firebase Cloud Functions (Node.js)
    └── ifttt_rain_hook.js          ← STUB: IFTTT rain integration, not yet wired up
```
