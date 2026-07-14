// Models/DeviceMeta.swift
// Mirrors /devices/pico-zone-1/meta in Firebase.
// The local_ip field is how the app knows which IP to probe for local mode.

import Foundation

struct DeviceMeta: Codable {
    var localIp:         String
    var firmwareVersion: String
    var deviceName:      String
}
