/**
 * cloud_functions/ifttt_rain_hook.js
 * IFTTT Rain Hook — Future Enhancement (v1.2)
 * ============================================
 * STATUS: STUB — returns HTTP 501. Not deployed.
 *
 * PURPOSE:
 *   Receives a webhook call from IFTTT when the Ambient Weather station
 *   reports rainfall, and writes a skip override to Firebase so the Pico
 *   skips its next scheduled run.
 *
 * WHY A CLOUD FUNCTION (not direct IFTTT → Firebase write):
 *   Firebase ID tokens expire every hour. IFTTT cannot refresh them.
 *   A Cloud Function using the Admin SDK has permanent database access
 *   and exposes a stable HTTPS URL. A shared secret in the request body
 *   prevents unauthorized calls.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * IMPLEMENTATION STEPS (when building v1.2):
 * ─────────────────────────────────────────────────────────────────────────
 *
 * 1. Generate a shared secret (40+ random chars) and store it:
 *      firebase functions:config:set ifttt.secret="YOUR_SECRET_HERE"
 *
 * 2. Implement the function body below (replace the 501 stub).
 *
 * 3. Deploy:
 *      firebase deploy --only functions:iftttRainHook
 *
 * 4. Copy the deployed function URL from Firebase Console →
 *    Functions → iftttRainHook → Trigger URL.
 *
 * 5. In IFTTT:
 *      Trigger:  Ambient Weather → "Any new weather data"
 *                Filter: RainIn > 0   (or RainRateIn > 0 for real-time)
 *      Action:   Webhooks → Make a web request
 *        URL:    https://us-central1-YOUR_PROJECT.cloudfunctions.net/iftttRainHook
 *        Method: POST
 *        Content-Type: application/json
 *        Body:
 *          {
 *            "secret":     "YOUR_SECRET_HERE",
 *            "rain_inches": "{{RainIn}}",
 *            "rain_rate":   "{{RainRateIn}}"
 *          }
 *
 *      IFTTT ingredient reference:
 *        {{RainIn}}      — daily rainfall accumulation in inches
 *        {{RainRateIn}}  — current rain rate in inches/hour
 *
 * ─────────────────────────────────────────────────────────────────────────
 * FIREBASE WRITE (what this function will do):
 * ─────────────────────────────────────────────────────────────────────────
 *
 *   /devices/pico-zone-1/overrides/
 *     skip_today:      true
 *     skip_date:       "YYYY-MM-DD"   ← today in UTC or local TZ
 *     skip_reason:     "rain"
 *     rain_inches:     0.45           ← float parsed from IFTTT body
 *     override_set_at: <unix epoch>
 *     override_set_by: "ifttt"
 *
 * ─────────────────────────────────────────────────────────────────────────
 * PICO v1.2 ENHANCEMENT SLOT (already stubbed in main.py):
 * ─────────────────────────────────────────────────────────────────────────
 *
 *   In override_reader.py, after confirming skip_reason == "rain":
 *     1. Read rain_inches from the overrides node
 *     2. Compare to config["rain_skip_threshold_inches"] (default 0.1)
 *     3. If rain_inches < threshold → do not skip (light drizzle)
 *     4. If rain_inches >= threshold → skip the run
 *
 *   Add to config.json:
 *     "rain_skip_threshold_inches": 0.1
 *
 *   This allows fine-tuning sensitivity from the iOS app's settings screen
 *   without reflashing firmware.
 */

const { onRequest }     = require("firebase-functions/v2/https");
const { initializeApp } = require("firebase-admin/app");
const { getDatabase }   = require("firebase-admin/database");

// initializeApp() is called in index.js — only call once per Functions instance.
// If deploying this file standalone, uncomment the line below:
// initializeApp();

const DEVICE_PATH = "devices/pico-zone-1";

/**
 * iftttRainHook
 *
 * HTTPS endpoint called by IFTTT Webhooks when rain is detected.
 * STUB — returns 501 until v1.2 implementation.
 */
exports.iftttRainHook = onRequest(
  { region: "us-central1" },
  async (req, res) => {
    // ── STUB ──────────────────────────────────────────────────────────────
    // Replace everything below this comment when implementing v1.2.
    // ──────────────────────────────────────────────────────────────────────

    res.status(501).json({
      error:   "Not yet implemented",
      message: "IFTTT rain hook is planned for v1.2. See ifttt_rain_hook.js for details.",
    });

    // ── IMPLEMENTATION TEMPLATE (uncomment for v1.2) ──────────────────────
    //
    // if (req.method !== "POST") {
    //   return res.status(405).json({ error: "Method not allowed" });
    // }
    //
    // const { secret, rain_inches, rain_rate } = req.body;
    //
    // // Validate shared secret
    // const expected = process.env.IFTTT_SECRET;
    // if (!expected || secret !== expected) {
    //   console.warn("iftttRainHook: invalid secret");
    //   return res.status(403).json({ error: "Forbidden" });
    // }
    //
    // const rainIn = parseFloat(rain_inches) || 0;
    //
    // // Build today's date string in Eastern time (adjust offset as needed)
    // const now       = new Date();
    // const estOffset = -5 * 60; // EST = UTC-5 (use -4 for EDT)
    // const local     = new Date(now.getTime() + estOffset * 60 * 1000);
    // const dateStr   = local.toISOString().slice(0, 10); // "YYYY-MM-DD"
    //
    // try {
    //   const db = getDatabase();
    //   await db.ref(`${DEVICE_PATH}/overrides`).set({
    //     skip_today:      true,
    //     skip_date:       dateStr,
    //     skip_reason:     "rain",
    //     rain_inches:     rainIn,
    //     override_set_at: Math.floor(Date.now() / 1000),
    //     override_set_by: "ifttt",
    //   });
    //   console.log(`Rain skip set for ${dateStr} — ${rainIn}" rain`);
    //   return res.status(200).json({ ok: true, skip_date: dateStr, rain_inches: rainIn });
    // } catch (err) {
    //   console.error("iftttRainHook DB write error:", err);
    //   return res.status(500).json({ error: "Database write failed" });
    // }
  }
);
