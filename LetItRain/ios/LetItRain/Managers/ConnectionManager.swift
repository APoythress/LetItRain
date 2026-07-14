// Managers/ConnectionManager.swift
// Determines whether the app is on the same Wi-Fi as the Pico (local mode)
// or away from home (remote mode).
//
// Detection flow:
//   1. Check NWPathMonitor — if not on Wi-Fi, switch to remote immediately
//   2. Read Pico's local IP from Firebase meta node
//   3. Probe GET http://{ip}/status with a 1.5s timeout
//   4. If probe succeeds → local mode; otherwise → remote mode
//
// Re-evaluated:
//   - Every 30 seconds while app is in foreground
//   - On every app foreground resume (sceneDidBecomeActive via NotificationCenter)
//   - After any failed local API call (fast fallback)

import Foundation
import Network
import Combine

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

// MARK: - ConnectionManager

@MainActor
final class ConnectionManager: ObservableObject {

    @Published private(set) var mode: AppConnectionMode = .remote
    @Published private(set) var isEvaluating: Bool = false

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
    func evaluate() {
        Task { await runEvaluation() }
    }

    // MARK: - Path monitor

    private func startPathMonitor() {
        let monitor = NWPathMonitor()
        monitor.pathUpdateHandler = { [weak self] path in
            Task { @MainActor [weak self] in
                self?.currentPath = path
                await self?.runEvaluation()
            }
        }
        monitor.start(queue: monitorQueue)
        pathMonitor = monitor
    }

    // MARK: - Periodic re-evaluation

    private func startPeriodicEvaluation() {
        evaluationTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            self?.evaluate()
        }
    }

    private func observeForegroundResume() {
        NotificationCenter.default.addObserver(
            forName: UIApplication.willEnterForegroundNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.evaluate()
        }
    }

    // MARK: - Core evaluation logic

    private func runEvaluation() async {
        guard !isEvaluating else { return }
        isEvaluating = true
        defer { isEvaluating = false }

        // Step 1: Must be on Wi-Fi
        guard let path = currentPath, path.usesInterfaceType(.wifi) else {
            mode = .remote
            return
        }

        // Step 2: Get the Pico's local IP from Firebase
        guard let meta = await metaProvider?(),
              !meta.localIp.isEmpty,
              meta.localIp != "0.0.0.0" else {
            mode = .remote
            return
        }

        // Step 3: Probe the Pico HTTP server with a 1.5s timeout
        let probeURL = URL(string: "http://\(meta.localIp)/status")!
        let config   = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest  = 1.5
        config.timeoutIntervalForResource = 1.5
        let session = URLSession(configuration: config)

        do {
            let (_, response) = try await session.data(from: probeURL)
            if let http = response as? HTTPURLResponse, http.statusCode == 200 {
                mode = .local(baseURL: "http://\(meta.localIp)")
                return
            }
        } catch {
            // Probe failed — not reachable on local network
        }

        mode = .remote
    }
}
