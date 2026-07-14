// Networking/LocalAPIClient.swift
// Communicates with the Pico W's HTTP JSON API over local Wi-Fi.
// Used only when ConnectionManager.mode == .local

import Foundation

// MARK: - Errors

enum LocalAPIError: LocalizedError {
    case notReachable
    case badResponse(Int)
    case decodingFailed
    case noData

    var errorDescription: String? {
        switch self {
        case .notReachable:      return "Cannot reach the sprinkler controller on your local network."
        case .badResponse(let c): return "Unexpected response from controller (HTTP \(c))."
        case .decodingFailed:    return "Could not read the controller's response."
        case .noData:            return "No data received from controller."
        }
    }
}

// MARK: - Client

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
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest  = 5
        config.timeoutIntervalForResource = 5
        self.session = URLSession(configuration: config)
    }

    // MARK: - Reads

    func fetchStatus() async throws -> DeviceStatus {
        try await get("/status")
    }

    func fetchConfig() async throws -> DeviceConfig {
        try await get("/config")
    }

    // MARK: - Control

    func sendStart(durationMinutes: Int) async throws {
        try await post("/start", body: ["duration_minutes": durationMinutes])
    }

    func sendStop() async throws {
        try await post("/stop", body: nil)
    }

    // MARK: - Config update

    func updateConfig(_ config: DeviceConfig) async throws {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(config)
        guard let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw LocalAPIError.decodingFailed
        }
        try await post("/config", body: dict)
    }

    // MARK: - Skip override

    func sendSkipToday() async throws {
        try await post("/skip-today", body: nil)
    }

    func cancelSkip() async throws {
        try await post("/cancel-skip", body: nil)
    }

    // MARK: - Private helpers

    private func get<T: Decodable>(_ path: String) async throws -> T {
        guard let url = URL(string: baseURL + path) else {
            throw LocalAPIError.notReachable
        }
        do {
            let (data, response) = try await session.data(from: url)
            try validateResponse(response)
            return try decode(T.self, from: data)
        } catch let error as LocalAPIError {
            throw error
        } catch {
            throw LocalAPIError.notReachable
        }
    }

    @discardableResult
    private func post(_ path: String, body: [String: Any]?) async throws -> Data {
        guard let url = URL(string: baseURL + path) else {
            throw LocalAPIError.notReachable
        }
        var request        = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if let body {
            request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        }

        do {
            let (data, response) = try await session.data(for: request)
            try validateResponse(response)
            return data
        } catch let error as LocalAPIError {
            throw error
        } catch {
            throw LocalAPIError.notReachable
        }
    }

    private func validateResponse(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else { return }
        guard (200..<300).contains(http.statusCode) else {
            throw LocalAPIError.badResponse(http.statusCode)
        }
    }

    private func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        do {
            return try decoder.decode(type, from: data)
        } catch {
            throw LocalAPIError.decodingFailed
        }
    }
}
