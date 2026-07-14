// Models/DeviceConfig.swift
// Mirrors the Pico's config.json / HTTP GET /config response.
// Only available in local mode — not exposed via Firebase.

import Foundation

struct DeviceConfig: Codable {
    var deviceName:                    String
    var relayPin:                      Int
    var relayActiveHigh:               Bool
    var manualDefaultDurationMinutes:  Int
    var schedule:                      ScheduleConfig

    // v1.2 future field — include now so no migration needed later
    var rainSkipThresholdInches:       Double?

    struct ScheduleConfig: Codable {
        var enabled:         Bool
        var days:            [Int]    // 0 = Mon … 6 = Sun
        var startHour:       Int
        var startMinute:     Int
        var durationMinutes: Int

        /// Human-readable day abbreviations for the selected days.
        var dayAbbreviations: [String] {
            let abbrevs = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            return days.compactMap { idx in
                guard idx >= 0, idx < abbrevs.count else { return nil }
                return abbrevs[idx]
            }
        }

        /// Formatted start time string e.g. "6:00 AM"
        var startTimeString: String {
            let hour12  = startHour % 12 == 0 ? 12 : startHour % 12
            let ampm    = startHour < 12 ? "AM" : "PM"
            return String(format: "%d:%02d %@", hour12, startMinute, ampm)
        }
    }

    // MARK: - Default config

    static var defaultConfig: DeviceConfig {
        DeviceConfig(
            deviceName:                   "Pico Sprinkler Controller",
            relayPin:                     15,
            relayActiveHigh:              true,
            manualDefaultDurationMinutes: 10,
            schedule: ScheduleConfig(
                enabled:         false,
                days:            [0, 2, 5],
                startHour:       6,
                startMinute:     0,
                durationMinutes: 15
            ),
            rainSkipThresholdInches: nil
        )
    }
}
