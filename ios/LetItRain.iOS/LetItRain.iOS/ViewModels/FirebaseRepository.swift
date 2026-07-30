// ViewModels/FirebaseRepository.swift
// Reads status, meta, zones, and schedule from Firebase (zones/schedule are
// read-only here -- the app never writes them; see DeviceViewModel).
// Writes: skip-for-N-days override, and the OTA "check now" request flag.

import Foundation
import Combine
import FirebaseDatabase

/// Thrown by any write attempted before `configure(deviceID:)` has run --
/// should never happen in practice, since ContentView gates on
/// AuthViewModel.deviceID before this repository is ever used, but this
/// avoids silently writing to a "devices/nil/..." path if that gate is
/// ever bypassed by a future change.
enum FirebaseRepositoryError: Error {
    case deviceNotConfigured
}

@MainActor
final class FirebaseRepository: ObservableObject {

    @Published var status:    DeviceStatus  = .placeholder
    @Published var meta:      DeviceMeta?   = nil
    @Published var config:    DeviceConfig? = nil
    @Published var otaStatus: OTAStatus     = .idle

    /// Set once via configure(deviceID:), after AuthViewModel resolves which
    /// device this signed-in user's account controls (users/{uid}/device_id).
    /// Was a hardcoded "devices/pico-zone-1" constant; now per-user so one
    /// Firebase project can host multiple people's devices.
    private var devicePath: String?
    private var handles: [DatabaseHandle] = []
    private let db = Database.database().reference()

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    func configure(deviceID: String) {
        devicePath = "devices/\(deviceID)"
    }

    // MARK: - Listeners

    func startListening() {
        guard let devicePath else {
            assertionFailure("FirebaseRepository.startListening() called before configure(deviceID:)")
            return
        }
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

    /// Tears down listeners and clears the resolved device -- call on
    /// sign-out. Without this, a sign-out/sign-in cycle within the same
    /// app session (e.g. a household switching between two people's
    /// devices) would leave the previous user's listeners attached
    /// indefinitely, alongside the newly signed-in user's, both writing
    /// into the same @Published properties.
    func reset() {
        stopListening()
        devicePath = nil
        status     = .placeholder
        meta       = nil
        config     = nil
        otaStatus  = .idle
    }

    // MARK: - Snapshot merging

    private func mergeZonesSnapshot(_ snap: DataSnapshot) {
        var zones: [ZoneConfig] = []

        if let dict = snap.value as? [String: Any] {
            for (key, val) in dict {
                guard let id = Int(key), let v = val as? [String: Any] else { continue }
                zones.append(ZoneConfig(
                    id:      id,
                    name:    v["name"]    as? String ?? "Zone \(id)",
                    pin:     v["pin"]     as? Int    ?? 0,
                    enabled: v["enabled"] as? Bool   ?? false
                ))
            }
        } else if let arr = snap.value as? [Any] {
            // Firebase coerces a node whose keys are purely sequential
            // numeric strings ("1".."5") into a JSON array instead of an
            // object -- index 0 is a null placeholder since there's no
            // zone id 0. Same quirk mergeScheduleSnapshot's slots parsing
            // below already accounts for; zones just needs it too.
            for (id, val) in arr.enumerated() {
                guard let v = val as? [String: Any] else { continue }
                zones.append(ZoneConfig(
                    id:      id,
                    name:    v["name"]    as? String ?? "Zone \(id)",
                    pin:     v["pin"]     as? Int    ?? 0,
                    enabled: v["enabled"] as? Bool   ?? false
                ))
            }
        } else {
            return
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
    //
    // Schedule/zone config is intentionally not writable here -- the app is
    // local-only for that (see DeviceViewModel.wireScheduleVM), and the
    // Firebase security rules enforce it too (zones/schedule .write is
    // owner-uid/Pico-only now, see root README).

    /// Skip the schedule for `days` days, starting today (inclusive) -- the
    /// out-of-town use case. `days: 1` behaves like the old single-day skip.
    func writeSkip(days: Int, reason: String = "manual_remote") async throws {
        guard let devicePath else { throw FirebaseRepositoryError.deviceNotConfigured }
        let until = dateString(daysFromToday: max(0, days - 1))
        try await db.child("\(devicePath)/overrides").setValue([
            "skip_active":     true,
            "skip_until":      until,
            "skip_reason":     reason,
            "override_set_at": ServerValue.timestamp(),
            "override_set_by": "app_remote",
        ] as [String: Any])
    }

    func cancelSkip() async throws {
        guard let devicePath else { throw FirebaseRepositoryError.deviceNotConfigured }
        try await db.child("\(devicePath)/overrides").updateChildValues([
            "skip_active": false,
            "skip_until":  NSNull(),
            "skip_reason": NSNull(),
        ] as [String: Any])
    }

    // MARK: - OTA update

    /// Ask the Pico to check for a firmware update right now instead of waiting
    /// for its periodic timer. The Pico clears `requested` as soon as it sees it.
    func requestUpdateCheck() async throws {
        guard let devicePath else { throw FirebaseRepositoryError.deviceNotConfigured }
        try await db.child("\(devicePath)/update").updateChildValues(["requested": true])
    }

    func currentMeta() async -> DeviceMeta? { meta }

    // MARK: - Helpers

    private func decode<T: Decodable>(_ type: T.Type, from dict: [String: Any]) -> T? {
        guard let data = try? JSONSerialization.data(withJSONObject: dict) else { return nil }
        return try? decoder.decode(type, from: data)
    }

    private func dateString(daysFromToday days: Int) -> String {
        let f = DateFormatter(); f.dateFormat = "yyyy-MM-dd"; f.timeZone = .current
        let date = Calendar.current.date(byAdding: .day, value: days, to: Date()) ?? Date()
        return f.string(from: date)
    }
}
