// Models/OTAStatus.swift
// Mirrors /devices/pico-zone-1/update in Firebase.
import Foundation

struct OTAStatus: Codable, Equatable {
    var status:  String    // "idle" | "checking" | "downloading" | "staged" | "error"
    var message: String?
    var requested: Bool?

    var isInProgress: Bool {
        status == "checking" || status == "downloading" || status == "staged"
    }

    static var idle: OTAStatus {
        OTAStatus(status: "idle", message: nil, requested: false)
    }
}
