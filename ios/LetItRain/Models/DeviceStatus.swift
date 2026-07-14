// Models/DeviceStatus.swift
// Mirrors the Firebase /devices/pico-zone-1/status node
// and the Pico HTTP GET /status response.

import Foundation

struct DeviceStatus: Codable {
    var isRunning:          Bool
    var currentMode:        String            // "idle" | "manual" | "scheduled"
    var runStartedAt:       TimeInterval?
    var runEndsAt:          TimeInterval?
    var lastRunStart:       TimeInterval?
    var lastRunEnd:         TimeInterval?
    var lastRunMode:        String?           // "manual" | "scheduled"
    var lastRunStatus:      String?           // "completed" | "manual_stop" | "skipped"
    var deviceOnline:       Bool
    var lastHeartbeat:      TimeInterval
    var activeSkip:         Bool
    var activeSkipReason:   String?           // "manual_remote" | "rain" | "manual_local"
    var firmwareVersion:    String?

    // MARK: - Derived helpers

    /// True when the device has sent a heartbeat within the last 30 seconds.
    var isRecentlyOnline: Bool {
        Date().timeIntervalSince1970 - lastHeartbeat < 30
    }

    /// Remaining seconds in the current run, or nil if not running.
    var remainingSeconds: TimeInterval? {
        guard isRunning, let endsAt = runEndsAt else { return nil }
        let remaining = endsAt - Date().timeIntervalSince1970
        return max(0, remaining)
    }

    /// Total duration of the current run in seconds, or nil if not running.
    var totalRunSeconds: TimeInterval? {
        guard isRunning, let startedAt = runStartedAt, let endsAt = runEndsAt else { return nil }
        return endsAt - startedAt
    }

    /// Fraction 0…1 of current run elapsed, or nil if not running.
    var runProgress: Double? {
        guard let total = totalRunSeconds, total > 0,
              let remaining = remainingSeconds else { return nil }
        return 1.0 - (remaining / total)
    }

    // MARK: - Placeholder for loading state

    static var placeholder: DeviceStatus {
        DeviceStatus(
            isRunning:       false,
            currentMode:     "idle",
            runStartedAt:    nil,
            runEndsAt:       nil,
            lastRunStart:    nil,
            lastRunEnd:      nil,
            lastRunMode:     nil,
            lastRunStatus:   nil,
            deviceOnline:    false,
            lastHeartbeat:   0,
            activeSkip:      false,
            activeSkipReason: nil,
            firmwareVersion: nil
        )
    }
}
