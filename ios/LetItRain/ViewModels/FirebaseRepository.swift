// ViewModels/FirebaseRepository.swift
// Reads device status and meta from Firebase Realtime Database.
// Used in remote mode. The Pico only WRITES to Firebase;
// the app only READS (plus one override write for skip-today).

import Foundation
import FirebaseDatabase
import FirebaseAuth

@MainActor
final class FirebaseRepository: ObservableObject {

    @Published var status: DeviceStatus = .placeholder
    @Published var meta:   DeviceMeta?  = nil

    private let devicePath = "devices/pico-zone-1"
    private var statusHandle: DatabaseHandle?
    private var metaHandle:   DatabaseHandle?
    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    // MARK: - Listeners

    func startListening() {
        let ref = Database.database().reference()

        // Status listener
        statusHandle = ref.child("\(devicePath)/status").observe(.value) { [weak self] snap in
            guard let self, let dict = snap.value as? [String: Any] else { return }
            Task { @MainActor [weak self] in
                self?.status = self?.decode(DeviceStatus.self, from: dict) ?? .placeholder
            }
        }

        // Meta listener (for local IP used by ConnectionManager)
        metaHandle = ref.child("\(devicePath)/meta").observe(.value) { [weak self] snap in
            guard let self, let dict = snap.value as? [String: Any] else { return }
            Task { @MainActor [weak self] in
                self?.meta = self?.decode(DeviceMeta.self, from: dict)
            }
        }
    }

    func stopListening() {
        let ref = Database.database().reference()
        if let h = statusHandle { ref.child("\(devicePath)/status").removeObserver(withHandle: h) }
        if let h = metaHandle   { ref.child("\(devicePath)/meta").removeObserver(withHandle: h) }
        statusHandle = nil
        metaHandle   = nil
    }

    // MARK: - Override writes (the ONLY writes the app makes to Firebase)

    /// Write a skip-today override to Firebase. The Pico reads this on the
    /// next scheduler tick and skips the scheduled run.
    func writeSkipToday(reason: String = "manual_remote") async throws {
        let dateStr = todayDateString()
        let ref = Database.database().reference()
            .child("\(devicePath)/overrides")

        try await ref.setValue([
            "skip_today":      true,
            "skip_date":       dateStr,
            "skip_reason":     reason,
            "override_set_at": ServerValue.timestamp(),
            "override_set_by": "app_remote",
        ] as [String: Any])
    }

    /// Clear a previously set skip override.
    func cancelSkip() async throws {
        let ref = Database.database().reference()
            .child("\(devicePath)/overrides")

        try await ref.updateChildValues([
            "skip_today":  false,
            "skip_date":   NSNull(),
            "skip_reason": NSNull(),
        ] as [String: Any])
    }

    // MARK: - Store FCM token

    func storeFCMToken(_ token: String) {
        guard let uid = Auth.auth().currentUser?.uid else { return }
        Database.database().reference()
            .child("users/\(uid)/fcm_token")
            .setValue(token)
    }

    // MARK: - Meta provider (for ConnectionManager)

    /// Returns current meta — used as the metaProvider closure in ConnectionManager.
    func currentMeta() async -> DeviceMeta? { meta }

    // MARK: - Decoding helper

    private func decode<T: Decodable>(_ type: T.Type, from dict: [String: Any]) -> T? {
        guard let data = try? JSONSerialization.data(withJSONObject: dict) else { return nil }
        return try? decoder.decode(type, from: data)
    }

    // MARK: - Date helper

    private func todayDateString() -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        formatter.timeZone   = .current
        return formatter.string(from: Date())
    }
}
