// Models/OTAStatus.swift
// Mirrors /devices/{device_id}/update in Firebase.
import Foundation

struct OTAStatus: Codable, Equatable {
    var status:  String    // "idle" | "checking" | "available" | "applying" | "error"
    var message: String?
    var requested: Bool?
    var applyRequested: Bool?
    var currentVersion: String?
    var availableVersion: String?
    var checkedAt: Double?

    var isInProgress: Bool {
        status == "checking" || status == "applying"
    }

    var isUpdateAvailable: Bool {
        status == "available" && availableVersion != nil
    }

    static var idle: OTAStatus {
        OTAStatus(status: "idle", message: nil, requested: false, applyRequested: false,
                  currentVersion: nil, availableVersion: nil, checkedAt: nil)
    }
}
