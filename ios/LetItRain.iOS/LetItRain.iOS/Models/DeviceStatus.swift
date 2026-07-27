// Models/DeviceStatus.swift
import Foundation

struct DeviceStatus: Codable {
    var isRunning:         Bool
    var activeZoneId:      Int?
    var currentMode:       String
    var runStartedAt:      TimeInterval?
    var runEndsAt:         TimeInterval?
    var lastRunStart:      TimeInterval?
    var lastRunEnd:        TimeInterval?
    var lastRunMode:       String?
    var lastRunZoneId:     Int?
    var lastRunStatus:     String?
    var deviceOnline:      Bool
    var lastSyncedEpoch:   TimeInterval
    var activeSkip:        Bool
    var activeSkipReason:  String?
    var firmwareVersion:   String?

    var isRecentlyOnline: Bool {
        // Locally this refreshes on every direct request (view appear, an
        // action, a mode change), so staleness there is never more than a
        // moment. Remotely, the Pico only syncs to Firebase every 15 min
        // (CLOUD_SYNC_INTERVAL in main.py) -- kept deliberately infrequent
        // so it doesn't wedge the Pico W's WiFi chip with constant TLS
        // traffic. 2x that (1h) absorbs a missed or late cycle without
        // flickering "offline" between normal syncs.
        Date().timeIntervalSince1970 - lastSyncedEpoch < 3600
    }

    var remainingSeconds: TimeInterval? {
        guard isRunning, let endsAt = runEndsAt else { return nil }
        return max(0, endsAt - Date().timeIntervalSince1970)
    }

    var totalRunSeconds: TimeInterval? {
        guard isRunning, let s = runStartedAt, let e = runEndsAt else { return nil }
        return e - s
    }

    var runProgress: Double? {
        guard let total = totalRunSeconds, total > 0,
              let remaining = remainingSeconds else { return nil }
        return 1.0 - (remaining / total)
    }

    static var placeholder: DeviceStatus {
        DeviceStatus(isRunning: false, activeZoneId: nil, currentMode: "idle",
                     runStartedAt: nil, runEndsAt: nil,
                     lastRunStart: nil, lastRunEnd: nil,
                     lastRunMode: nil, lastRunZoneId: nil, lastRunStatus: nil,
                     deviceOnline: false, lastSyncedEpoch: 0,
                     activeSkip: false, activeSkipReason: nil, firmwareVersion: nil)
    }
}
