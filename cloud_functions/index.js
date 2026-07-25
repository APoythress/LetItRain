/**
 * cloud_functions/index.js
 * LetItRain Firebase Cloud Functions
 *
 * Deployed functions:
 *   onStatusChange  — sends push notifications when run starts/stops
 *
 * Stub (not deployed):
 *   iftttRainHook   — see ifttt_rain_hook.js
 *
 * Deploy:
 *   cd cloud_functions
 *   npm install
 *   firebase deploy --only functions
 *
 * Prerequisites:
 *   firebase login
 *   firebase use --add   (select your LetItRain project)
 */

const { onValueUpdated } = require("firebase-functions/v2/database");
const { initializeApp }  = require("firebase-admin/app");
const { getMessaging }   = require("firebase-admin/messaging");
const { getDatabase }    = require("firebase-admin/database");

initializeApp();

const DEVICE_PATH = "devices/pico-zone-1";

/**
 * onStatusChange
 *
 * Fires whenever /devices/pico-zone-1/status changes.
 * Sends an FCM push notification to the registered iOS device when:
 *   - is_running flips false → true  (run started)
 *   - is_running flips true → false  (run stopped)
 *
 * The FCM token is stored at /users/{uid}/fcm_token by the iOS app.
 *
 * HOW TO FIND YOUR USER UID:
 *   Firebase Console → Authentication → Users table → copy the UID column
 *   value for your personal account. Set it as an environment variable:
 *
 *     firebase functions:config:set app.user_uid="YOUR_UID_HERE"
 *
 *   Or hardcode it temporarily during development (replace before committing).
 */
exports.onStatusChange = onValueUpdated(
  {
    ref:      `${DEVICE_PATH}/status`,
    region:   "us-central1",
    instance: process.env.FIREBASE_DATABASE_INSTANCE || undefined,
  },
  async (event) => {
    const before = event.data.before.val();
    const after  = event.data.after.val();

    if (!before || !after) return;

    const wasRunning = before.is_running === true;
    const isRunning  = after.is_running  === true;

    if (wasRunning === isRunning) return; // no change in run state

    // Determine notification content
    let title, body;
    if (!wasRunning && isRunning) {
      const mode = after.current_mode || "manual";
      title = "💧 LetItRain";
      body  = `Zone 1 started (${mode})`;
    } else if (wasRunning && !isRunning) {
      const status = after.last_run_status || "completed";
      title = "✅ LetItRain";
      body  = `Zone 1 finished — ${status}`;
    }

    if (!title) return;

    // Read all FCM tokens from /users/*/fcm_token
    // (supports multiple devices for the same user in future)
    try {
      const db      = getDatabase();
      const snap    = await db.ref("users").get();
      const users   = snap.val();
      if (!users) return;

      const tokens = [];
      for (const uid of Object.keys(users)) {
        const token = users[uid]?.fcm_token;
        if (token) tokens.push(token);
      }

      if (tokens.length === 0) {
        console.log("No FCM tokens registered — skipping notification");
        return;
      }

      const messaging = getMessaging();
      const results   = await messaging.sendEachForMulticast({
        tokens,
        notification: { title, body },
        apns: {
          payload: {
            aps: {
              sound: "default",
              badge: 0,
            },
          },
        },
      });

      console.log(
        `Notification sent: "${body}" → ${results.successCount} ok, ${results.failureCount} failed`
      );
    } catch (err) {
      console.error("onStatusChange error:", err);
    }
  }
);
