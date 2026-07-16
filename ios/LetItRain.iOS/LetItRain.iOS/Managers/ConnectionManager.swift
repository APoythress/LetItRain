// Managers/ConnectionManager.swift
// Determines whether the app is on the same Wi-Fi as the Pico (local mode)
// or away from home (remote mode).
//
// Detection flow:
//   1. Check NWPathMonitor — if there's no network connectivity at all,
//      switch to remote immediately. We deliberately do NOT require the
//      active interface to be reported as Wi-Fi: a VPN, Private Relay, or
//      similar tunnel makes NWPath report a virtual (utun) interface as
//      primary even though the phone is physically on the same Wi-Fi as the
//      Pico, which would otherwise produce a false "remote" verdict.
//   2. Read Pico's local IP from Firebase meta node
//   3. Probe GET http://{ip}/status with a short timeout
//   4. If probe succeeds → local mode; otherwise → remote mode
//
// Re-evaluated:
//   - Every 30 seconds while app is in foreground
//   - On every app foreground resume (sceneDidBecomeActive via NotificationCenter)
//   - After any failed local API call (fast fallback)
//   - The moment the Pico's meta/IP first loads or changes (DeviceViewModel)
//
// Diagnostics: every evaluation appends a `ConnectionDiagnostics.Entry` to
// `history` (newest first, capped) and updates `lastEntry`. Both are
// @Published so a debug UI (see ConnectionDiagnosticsView) can render the
// full step-by-step reasoning live, without needing an attached debugger —
// this matters because the most common real failure (denied Local Network
// permission) otherwise fails completely silently on-device.

import Foundation
import Network
import Combine
import UIKit
import os

// MARK: - Mode

enum AppConnectionMode: Equatable {
    case local(baseURL: String)
    case remote
    case offline

    var isLocal: Bool {
        if case .local = self { return true }
        return false
    }

    var baseURL: String? {
        if case .local(let url) = self { return url }
        return nil
    }

    var displayName: String {
        switch self {
        case .local:   return "Local"
        case .remote:  return "Remote"
        case .offline: return "Offline"
        }
    }
}

// MARK: - Diagnostics

/// A single, human-readable trace of one evaluation pass, shown in
/// ConnectionDiagnosticsView so the failure point is visible on-device.
struct ConnectionDiagnostics: Identifiable {
    let id = UUID()
    let timestamp: Date
    let trigger: String

    var pathStatus: String = "—"
    var interfaceTypes: String = "—"

    var metaFound: Bool = false
    var localIp: String = "—"

    var probeAttempted: Bool = false
    var probeURL: String = "—"
    var probeDurationMs: Int? = nil
    var probeOutcome: String = "—"

    var finalMode: String = "—"
    var stoppedAt: String = "—"   // which step short-circuited, if any

    static func starting(trigger: String) -> ConnectionDiagnostics {
        ConnectionDiagnostics(timestamp: Date(), trigger: trigger)
    }
}

// MARK: - ConnectionManager

@MainActor
final class ConnectionManager: ObservableObject {

    @Published private(set) var mode: AppConnectionMode = .remote
    @Published private(set) var isEvaluating: Bool = false

    /// Most recent evaluation's full trace.
    @Published private(set) var lastDiagnostics: ConnectionDiagnostics?
    /// Rolling history, newest first, capped at 25 entries.
    @Published private(set) var history: [ConnectionDiagnostics] = []

    private let logger = Logger(subsystem: "com.thetributeco.letitrain", category: "ConnectionManager")

    private var pathMonitor: NWPathMonitor?
    private var monitorQueue = DispatchQueue(label: "com.letitrain.netmonitor")
    private var evaluationTimer: Timer?
    private var currentPath: NWPath?

    /// Injected by ContentView after FirebaseRepository is created.
    /// Weak to avoid retain cycle.
    var metaProvider: (() async -> DeviceMeta?)? = nil

    init() {
        startPathMonitor()
        startPeriodicEvaluation()
        observeForegroundResume()
    }

    deinit {
        evaluationTimer?.invalidate()
        pathMonitor?.cancel()
    }

    // MARK: - Public

    /// Trigger a manual re-evaluation (e.g. after a failed local request).
    func evaluate(reason: String = "manual") {
        logger.debug("evaluate() requested — trigger: \(reason, privacy: .public)")
        Task { await runEvaluation(trigger: reason) }
    }

    // MARK: - Path monitor

    private func startPathMonitor() {
        let monitor = NWPathMonitor()
        monitor.pathUpdateHandler = { [weak self] path in
            Task { @MainActor [weak self] in
                self?.currentPath = path
                self?.logger.debug("""
                    NWPath update — status: \(String(describing: path.status), privacy: .public) \
                    wifi: \(path.usesInterfaceType(.wifi)) \
                    cellular: \(path.usesInterfaceType(.cellular)) \
                    wired: \(path.usesInterfaceType(.wiredEthernet)) \
                    other: \(path.usesInterfaceType(.other))
                    """)
                await self?.runEvaluation(trigger: "path change")
            }
        }
        monitor.start(queue: monitorQueue)
        pathMonitor = monitor
    }

    // MARK: - Periodic re-evaluation

    private func startPeriodicEvaluation() {
        evaluationTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            self?.evaluate(reason: "30s timer")
        }
    }

    private func observeForegroundResume() {
        NotificationCenter.default.addObserver(
            forName: UIApplication.willEnterForegroundNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.evaluate(reason: "foreground resume")
        }
    }

    // MARK: - Core evaluation logic

    private func runEvaluation(trigger: String) async {
        guard !isEvaluating else {
            logger.debug("runEvaluation skipped — already evaluating (trigger: \(trigger, privacy: .public))")
            return
        }
        isEvaluating = true
        defer { isEvaluating = false }

        var trace = ConnectionDiagnostics.starting(trigger: trigger)
        defer { record(trace) }

        // Step 1: Must have some network connectivity. Deliberately not
        // gated on `path.usesInterfaceType(.wifi)` — see comment at top of
        // file for why that's unreliable with VPNs/Private Relay active.
        guard let path = currentPath else {
            trace.pathStatus = "no path yet"
            trace.stoppedAt = "1: no NWPath captured yet"
            mode = .remote
            trace.finalMode = mode.displayName
            return
        }

        trace.pathStatus = "\(path.status)"
        trace.interfaceTypes = [
            path.usesInterfaceType(.wifi)          ? "wifi"     : nil,
            path.usesInterfaceType(.cellular)       ? "cellular" : nil,
            path.usesInterfaceType(.wiredEthernet)  ? "wired"    : nil,
            path.usesInterfaceType(.other)          ? "other"    : nil,
        ].compactMap { $0 }.joined(separator: ", ").isEmpty
            ? "none reported"
            : [
                path.usesInterfaceType(.wifi)          ? "wifi"     : nil,
                path.usesInterfaceType(.cellular)       ? "cellular" : nil,
                path.usesInterfaceType(.wiredEthernet)  ? "wired"    : nil,
                path.usesInterfaceType(.other)          ? "other"    : nil,
              ].compactMap { $0 }.joined(separator: ", ")

        guard path.status == .satisfied else {
            trace.stoppedAt = "1: NWPath not satisfied (no connectivity at all)"
            mode = .remote
            trace.finalMode = mode.displayName
            return
        }

        // Step 2: Get the Pico's local IP from Firebase
        let meta = await metaProvider?()
        trace.metaFound = meta != nil
        trace.localIp = meta?.localIp ?? "nil (metaProvider returned nothing)"

        guard let meta, !meta.localIp.isEmpty, meta.localIp != "0.0.0.0" else {
            trace.stoppedAt = "2: no usable local IP from Firebase meta yet"
            mode = .remote
            trace.finalMode = mode.displayName
            return
        }

        // Step 3: Probe the Pico HTTP server. Generous timeout since the
        // Pico's single-threaded HTTP server can be slow to accept a new
        // connection if it's mid-request.
        let probeURL = URL(string: "http://\(meta.localIp)/status")!
        trace.probeAttempted = true
        trace.probeURL = probeURL.absoluteString

        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest  = 3
        config.timeoutIntervalForResource = 3
        let session = URLSession(configuration: config)

        let start = Date()
        do {
            let (_, response) = try await session.data(from: probeURL)
            trace.probeDurationMs = Int(Date().timeIntervalSince(start) * 1000)
            if let http = response as? HTTPURLResponse {
                trace.probeOutcome = "HTTP \(http.statusCode)"
                if http.statusCode == 200 {
                    mode = .local(baseURL: "http://\(meta.localIp)")
                    trace.finalMode = mode.displayName
                    trace.stoppedAt = "3: probe succeeded → local"
                    return
                }
            } else {
                trace.probeOutcome = "non-HTTP response"
            }
        } catch {
            trace.probeDurationMs = Int(Date().timeIntervalSince(start) * 1000)
            // Logged (rather than swallowed) because the most common real
            // failure is the user denying the "Local Network" permission
            // prompt, which fails silently and looks identical to the Pico
            // genuinely being unreachable. NSURLErrorDomain -1004/-1009 are
            // generic connection-refused/offline codes; a permission denial
            // typically surfaces as -1004 or -65554 ("No Network Route")
            // rather than a distinct error, so we log full details.
            let nsError = error as NSError
            trace.probeOutcome = "\(nsError.domain) \(nsError.code): \(nsError.localizedDescription)"
            logger.error("""
                Local probe FAILED — url: \(probeURL.absoluteString, privacy: .public) \
                error: \(nsError.domain, privacy: .public) \(nsError.code) \
                \(nsError.localizedDescription, privacy: .public)
                """)
        }

        trace.stoppedAt = "3: probe did not return a healthy 200"
        mode = .remote
        trace.finalMode = mode.displayName
    }

    private func record(_ entry: ConnectionDiagnostics) {
        lastDiagnostics = entry
        history.insert(entry, at: 0)
        if history.count > 25 { history.removeLast(history.count - 25) }
        logger.debug("""
            Evaluation done — trigger: \(entry.trigger, privacy: .public) \
            path: \(entry.pathStatus, privacy: .public) \
            interfaces: \(entry.interfaceTypes, privacy: .public) \
            ip: \(entry.localIp, privacy: .public) \
            probe: \(entry.probeOutcome, privacy: .public) \
            → mode: \(entry.finalMode, privacy: .public) \
            (\(entry.stoppedAt, privacy: .public))
            """)
    }
}
