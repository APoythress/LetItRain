// Networking/LocalAPIClient.swift
// Multi-zone aware local HTTP client.

import Foundation

enum LocalAPIError: LocalizedError {
    case notReachable
    case badResponse(Int)
    case decodingFailed

    var errorDescription: String? {
        switch self {
        case .notReachable:       return "Cannot reach the controller on your local network."
        case .badResponse(let c): return "Unexpected response from controller (HTTP \(c))."
        case .decodingFailed:     return "Could not read the controller's response."
        }
    }
}

final class LocalAPIClient {

    private let baseURL: String
    private let session: URLSession

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    init(baseURL: String) {
        self.baseURL = baseURL.hasSuffix("/") ? String(baseURL.dropLast()) : baseURL
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest  = 5
        cfg.timeoutIntervalForResource = 5
        session = URLSession(configuration: cfg)
    }

    func fetchStatus() async throws -> DeviceStatus  { try await get("/status") }
    func fetchConfig() async throws -> DeviceConfig  { try await get("/config") }

    func sendStart(zoneId: Int, durationMinutes: Int) async throws {
        try await post("/start", body: ["zone_id": zoneId, "duration_minutes": durationMinutes])
    }

    func sendStop() async throws { try await post("/stop", body: nil) }

    func updateConfig(_ config: DeviceConfig) async throws {
        // Build the dict manually to match Pico's snake_case JSON expectation
        let zones: [[String: Any]] = config.zones.map {
            ["id": $0.id, "name": $0.name, "pin": $0.pin, "enabled": $0.enabled]
        }
        var scheduleDict: [String: Any] = [:]
        for day in Weekday.allCases {
            let d = config.schedule[day]
            let slots: [[String: Any]] = d.slots.map {
                ["zone": $0.zone, "start_hour": $0.startHour,
                 "start_minute": $0.startMinute, "duration_minutes": $0.durationMinutes]
            }
            scheduleDict[day.rawValue] = ["enabled": d.enabled, "slots": slots]
        }
        let body: [String: Any] = [
            "device_name":                    config.deviceName,
            "zone_count":                     config.zoneCount,
            "zones":                          zones,
            "schedule":                       scheduleDict,
            "manual_default_duration_minutes": config.manualDefaultDurationMinutes,
        ]
        try await post("/config", body: body)
    }

    func sendSkipToday() async throws  { try await post("/skip-today",   body: nil) }
    func cancelSkip()   async throws   { try await post("/cancel-skip",  body: nil) }
    func sendResyncTime()  async throws { try await post("/resync-time",  body: nil) }

    // MARK: - Internals

    private func get<T: Decodable>(_ path: String) async throws -> T {
        guard let url = URL(string: baseURL + path) else { throw LocalAPIError.notReachable }
        do {
            let (data, response) = try await session.data(from: url)
            try validateResponse(response)
            return try decoder.decode(T.self, from: data)
        } catch let e as LocalAPIError { throw e
        } catch { throw LocalAPIError.notReachable }
    }

    @discardableResult
    private func post(_ path: String, body: [String: Any]?) async throws -> Data {
        guard let url = URL(string: baseURL + path) else { throw LocalAPIError.notReachable }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let body { req.httpBody = try? JSONSerialization.data(withJSONObject: body) }
        do {
            let (data, response) = try await session.data(for: req)
            try validateResponse(response)
            return data
        } catch let e as LocalAPIError { throw e
        } catch { throw LocalAPIError.notReachable }
    }

    private func validateResponse(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse,
              (200..<300).contains(http.statusCode) else {
            throw LocalAPIError.badResponse((response as? HTTPURLResponse)?.statusCode ?? 0)
        }
    }
}
