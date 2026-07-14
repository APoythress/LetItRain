// ViewModels/FirebaseRepository.swift
// Reads status, meta, zones, and schedule from Firebase.
// Writes overrides (skip-today) and schedule/zone config.

import Foundation
import Combine
import FirebaseDatabase
import FirebaseAuth

@MainActor
final class FirebaseRepository: ObservableObject {

    @Published var status:    DeviceStatus  = .placeholder
    @Published var meta:      DeviceMeta?   = nil
    @Published var config:    DeviceConfig? = nil
    @Published var otaStatus: OTAStatus     = .idle

    private let devicePath = "devices/pico-zone-1"
    private var handles: [DatabaseHandle] = []
    private let db = Database.database().reference()

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    // MARK: - Listeners

    func startListening() {
        // Status
        let sh = db.child("\(devicePath)/status").observe(.value) { [weak self] snap in
            guard let self, let dict = snap.value as? [String: Any] else { return }
            Task { @MainActor [weak self] in
                self?.status = self?.decode(DeviceStatus.self, from: dict) ?? .placeholder
            }
        }

        // Meta
        let mh = db.child("\(devicePath)/meta").observe(.value) { [weak self] snap in
            guard let self, let dict = snap.value as? [String: Any] else { return }
            Task { @MainActor [weak self] in
                self?.meta = self?.decode(DeviceMeta.self, from: dict)
            }
        }

        // Zones + schedule → build DeviceConfig
        let zh = db.child("\(devicePath)/zones").observe(.value) { [weak self] snap in
            guard let self else { return }
            Task { @MainActor [weak self] in
                self?.mergeZonesSnapshot(snap)
            }
        }
        let sch = db.child("\(devicePath)/schedule").observe(.value) { [weak self] snap in
            guard let self else { return }
            Task { @MainActor [weak self] in
                self?.mergeScheduleSnapshot(snap)
            }
        }

        // OTA update status
        let uh = db.child("\(devicePath)/update").observe(.value) { [weak self] snap in
            guard let self, let dict = snap.value as? [String: Any] else { return }
            Task { @MainActor [weak self] in
                self?.otaStatus = self?.decode(OTAStatus.self, from: dict) ?? .idle
            }
        }

        handles = [sh, mh, zh, sch, uh]
    }

    func stopListening() {
        handles.forEach { db.removeObserver(withHandle: $0) }
        handles = []
    }

    // MARK: - Snapshot merging

    private func mergeZonesSnapshot(_ snap: DataSnapshot) {
        guard let dict = snap.value as? [String: Any] else { return }
        var zones: [ZoneConfig] = []
        for (key, val) in dict {
            guard let id = Int(key), let v = val as? [String: Any] else { continue }
            zones.append(ZoneConfig(
                id:      id,
                name:    v["name"]    as? String ?? "Zone \(id)",
                pin:     v["pin"]     as? Int    ?? 0,
                enabled: v["enabled"] as? Bool   ?? false
            ))
        }
        zones.sort { $0.id < $1.id }
        var current = config ?? .defaultConfig
        current.zones      = zones
        current.zoneCount  = zones.filter(\.enabled).count
        config = current
    }

    private func mergeScheduleSnapshot(_ snap: DataSnapshot) {
        guard let dict = snap.value as? [String: Any] else { return }
        var week = config?.schedule ?? .empty
        for day in Weekday.allCases {
            guard let dayDict = dict[day.rawValue] as? [String: Any] else { continue }
            let enabled = dayDict["enabled"] as? Bool ?? false
            var slots: [ScheduleSlot] = []

            // Firebase returns slots as dict {"0": {...}, "1": {...}} or array
            if let slotsDict = dayDict["slots"] as? [String: Any] {
                let sorted = slotsDict.keys.sorted { ($0.compare($1, options: .numeric)) == .orderedAscending }
                for k in sorted {
                    if let s = slotsDict[k] as? [String: Any], let slot = slotFrom(s) {
                        slots.append(slot)
                    }
                }
            } else if let slotsArr = dayDict["slots"] as? [[String: Any]] {
                slots = slotsArr.compactMap { slotFrom($0) }
            }

            week[day] = DaySchedule(enabled: enabled, slots: slots)
        }
        var current = config ?? .defaultConfig
        current.schedule = week
        config = current
    }

    private func slotFrom(_ d: [String: Any]) -> ScheduleSlot? {
        guard let zone = d["zone"] as? Int,
              let h    = d["start_hour"] as? Int,
              let m    = d["start_minute"] as? Int,
              let dur  = d["duration_minutes"] as? Int else { return nil }
        return ScheduleSlot(zone: zone, startHour: h, startMinute: m, durationMinutes: dur)
    }

    // MARK: - Writes

    /// Write entire schedule + zones to Firebase. Called from ScheduleViewModel on save.
    func writeConfig(_ config: DeviceConfig) async throws {
        // Zones
        var zonesDict: [String: Any] = [:]
        for z in config.zones {
            zonesDict["\(z.id)"] = ["name": z.name, "pin": z.pin, "enabled": z.enabled]
        }
        try await db.child("\(devicePath)/zones").setValue(zonesDict)

        // Schedule
        var scheduleDict: [String: Any] = [:]
        for day in Weekday.allCases {
            let d     = config.schedule[day]
            var slots: [String: Any] = [:]
            for (i, slot) in d.slots.enumerated() {
                slots["\(i)"] = [
                    "zone":               slot.zone,
                    "start_hour":         slot.startHour,
                    "start_minute":       slot.startMinute,
                    "duration_minutes":   slot.durationMinutes,
                ]
            }
            scheduleDict[day.rawValue] = ["enabled": d.enabled, "slots": slots]
        }
        try await db.child("\(devicePath)/schedule").setValue(scheduleDict)
    }

    /// Skip-today override.
    func writeSkipToday(reason: String = "manual_remote") async throws {
        let dateStr = todayDateString()
        try await db.child("\(devicePath)/overrides").setValue([
            "skip_today":      true,
            "skip_date":       dateStr,
            "skip_reason":     reason,
            "override_set_at": ServerValue.timestamp(),
            "override_set_by": "app_remote",
        ] as [String: Any])
    }

    func cancelSkip() async throws {
        try await db.child("\(devicePath)/overrides").updateChildValues([
            "skip_today":  false,
            "skip_date":   NSNull(),
            "skip_reason": NSNull(),
        ] as [String: Any])
    }

    // MARK: - OTA update

    /// Ask the Pico to check for a firmware update right now instead of waiting
    /// for its periodic timer. The Pico clears `requested` as soon as it sees it.
    func requestUpdateCheck() async throws {
        try await db.child("\(devicePath)/update").updateChildValues(["requested": true])
    }

    // MARK: - FCM token

    func storeFCMToken(_ token: String) {
        guard let uid = Auth.auth().currentUser?.uid else { return }
        db.child("users/\(uid)/fcm_token").setValue(token)
    }

    func currentMeta() async -> DeviceMeta? { meta }

    // MARK: - Helpers

    private func decode<T: Decodable>(_ type: T.Type, from dict: [String: Any]) -> T? {
        guard let data = try? JSONSerialization.data(withJSONObject: dict) else { return nil }
        return try? decoder.decode(type, from: data)
    }

    private func todayDateString() -> String {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; f.timeZone = .current
        return f.string(from: Date())
    }
}
