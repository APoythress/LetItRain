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
    var lastHeartbeat:     TimeInterval
    var activeSkip:        Bool
    var activeSkipReason:  String?
    var firmwareVersion:   String?

    var isRecentlyOnline: Bool {
        Date().timeIntervalSince1970 - lastHeartbeat < 30
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
                     deviceOnline: false, lastHeartbeat: 0,
                     activeSkip: false, activeSkipReason: nil, firmwareVersion: nil)
    }
}
