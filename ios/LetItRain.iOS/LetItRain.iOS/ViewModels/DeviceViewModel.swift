// ViewModels/DeviceViewModel.swift
// Unified ViewModel. Mode-aware. Delegates schedule logic to ScheduleViewModel.

import Foundation
import Combine

/// Thrown by any action that requires local Wi-Fi (schedule save, manual
/// start/stop) when attempted without a local connection.
private struct LocalOnlyError: LocalizedError {
    var errorDescription: String? { "Requires local Wi-Fi connection." }
}

@MainActor
final class DeviceViewModel: ObservableObject {

    @Published var status:          DeviceStatus  = .placeholder
    @Published var config:          DeviceConfig? = nil
    @Published var isLoading:       Bool          = false
    @Published var errorMessage:    String?       = nil
    @Published var successMessage:  String?       = nil
    @Published var otaStatus:       OTAStatus     = .idle

    let scheduleVM = ScheduleViewModel()

    private let connectionManager:  ConnectionManager
    private let firebaseRepository: FirebaseRepository
    private var localClient:        LocalAPIClient?
    private var cancellables        = Set<AnyCancellable>()
    private var localRefreshTimer:  Timer?

    init(connectionManager: ConnectionManager, firebaseRepository: FirebaseRepository) {
        self.connectionManager  = connectionManager
        self.firebaseRepository = firebaseRepository
        observeModeChanges()
        observeFirebaseStatus()
        observeFirebaseConfig()
        observeFirebaseOTAStatus()
        observeMetaAvailability()
        wireScheduleVM()
    }

    // MARK: - Observation

    private func observeMetaAvailability() {
        // The connection manager's periodic timer alone can leave the app
        // showing "Remote" for up to 30s after launch, since on a cold start
        // the Pico's local IP usually hasn't arrived from Firebase yet when
        // the first evaluation runs. Re-evaluate the moment it does.
        firebaseRepository.$meta
            .receive(on: DispatchQueue.main)
            .sink { [weak self] _ in self?.connectionManager.evaluate(reason: "meta updated") }
            .store(in: &cancellables)
    }

    private func observeModeChanges() {
        connectionManager.$mode
            .receive(on: DispatchQueue.main)
            .sink { [weak self] newMode in self?.handleModeChange(newMode) }
            .store(in: &cancellables)
    }

    private func handleModeChange(_ mode: AppConnectionMode) {
        switch mode {
        case .local(let baseURL):
            localClient = LocalAPIClient(baseURL: baseURL)
            startLocalPolling()
        case .remote, .offline:
            localClient = nil
            stopLocalPolling()
            config = firebaseRepository.config
        }
    }

    private func observeFirebaseStatus() {
        firebaseRepository.$status
            .receive(on: DispatchQueue.main)
            .sink { [weak self] s in
                guard let self, !self.connectionManager.mode.isLocal else { return }
                self.status = s
            }
            .store(in: &cancellables)
    }

    private func observeFirebaseConfig() {
        firebaseRepository.$config
            .receive(on: DispatchQueue.main)
            .sink { [weak self] cfg in
                guard let self, let cfg else { return }
                if !self.connectionManager.mode.isLocal {
                    self.config = cfg
                    self.scheduleVM.load(from: cfg)
                }
            }
            .store(in: &cancellables)
    }

    private func observeFirebaseOTAStatus() {
        // OTA status only ever comes from Firebase -- the Pico has no local
        // HTTP endpoint for it -- so mirror it regardless of local/remote mode.
        firebaseRepository.$otaStatus
            .receive(on: DispatchQueue.main)
            .sink { [weak self] s in self?.otaStatus = s }
            .store(in: &cancellables)
    }

    // Schedule editing is local-only -- there is no remote-write fallback
    // here on purpose (see root README's Firebase rules note: zones/schedule
    // .write is owner-uid/Pico-only now, so a remote write would be
    // rejected by the rules even if attempted). ScheduleView is only ever
    // shown while connectionManager.mode.isLocal (see HomeView), so the
    // no-client branch below should never actually fire in practice; it's
    // a clear error rather than a silent no-op if it somehow does.
    private func wireScheduleVM() {
        scheduleVM.onSave = { [weak self] updatedConfig in
            guard let self, let client = self.localClient else {
                throw LocalOnlyError()
            }
            try await client.updateConfig(updatedConfig)
            self.config = updatedConfig
        }
    }

    // MARK: - Local polling

    // The Pico's HTTP server handles exactly one connection at a time --
    // there's no real concurrency on that side, and every request is a
    // resource competing with its Firebase/TLS traffic for very limited RAM.
    // The app tolerates 30-45s of staleness on everything, so this polls
    // status every 30s and config every other tick (60s -- it rarely
    // changes anyway), one request at a time rather than concurrently.
    private var localPollCount = 0

    private func startLocalPolling() {
        stopLocalPolling()
        localPollCount = 0
        localRefreshTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in await self?.refreshLocal() }
        }
        Task { await refreshLocal() }
    }

    private func stopLocalPolling() {
        localRefreshTimer?.invalidate()
        localRefreshTimer = nil
    }

    private func refreshLocal() async {
        guard let client = localClient else { return }
        do {
            let newStatus = try await client.fetchStatus()
            status = newStatus

            localPollCount += 1
            guard localPollCount % 2 == 0 || config == nil else { return }

            let newConfig = try await client.fetchConfig()
            config = newConfig
            if !scheduleVM.hasUnsavedChanges {
                scheduleVM.load(from: newConfig)
            }
        } catch {
            connectionManager.evaluate(reason: "local poll failed")
        }
    }

    // MARK: - Actions

    func refresh() {
        Task {
            isLoading = true
            defer { isLoading = false }
            if localClient != nil { await refreshLocal() }
        }
    }

    func startManual(zoneId: Int, durationMinutes: Int) {
        guard let client = localClient else {
            errorMessage = "Manual control requires local Wi-Fi connection."
            return
        }
        Task {
            isLoading = true
            do {
                try await client.sendStart(zoneId: zoneId, durationMinutes: durationMinutes)
                await refreshLocal()
            } catch { handleError(error) }
            isLoading = false
        }
    }

    func stop() {
        guard let client = localClient else { return }
        Task {
            isLoading = true
            do {
                try await client.sendStop()
                await refreshLocal()
            } catch { handleError(error) }
            isLoading = false
        }
    }

    /// Local-only instant skip. Remote uses `skipForDays(_:)` instead, since
    /// "skip today" alone isn't useful when you won't be back to check the
    /// app again before tomorrow's run.
    func skipToday() {
        guard let client = localClient else {
            errorMessage = "Requires local Wi-Fi connection."
            return
        }
        Task {
            isLoading = true
            do {
                try await client.sendSkipToday()
                await refreshLocal()
                successMessage = "Today's scheduled run will be skipped."
            } catch { handleError(error) }
            isLoading = false
        }
    }

    /// Remote-only: skip the schedule for the next `days` days (inclusive of
    /// today) -- the out-of-town use case.
    func skipForDays(_ days: Int) {
        Task {
            isLoading = true
            do {
                try await firebaseRepository.writeSkip(days: days)
                successMessage = days <= 1
                    ? "Today's scheduled run will be skipped."
                    : "Schedule skipped for \(days) days."
            } catch { handleError(error) }
            isLoading = false
        }
    }

    func cancelSkip() {
        Task {
            isLoading = true
            do {
                if let client = localClient {
                    try await client.cancelSkip()
                    await refreshLocal()
                } else {
                    try await firebaseRepository.cancelSkip()
                }
                successMessage = "Skip cancelled."
            } catch { handleError(error) }
            isLoading = false
        }
    }

    func checkForUpdate() {
        Task {
            isLoading = true
            do {
                try await firebaseRepository.requestUpdateCheck()
                successMessage = "Checking for update..."
            } catch { handleError(error) }
            isLoading = false
        }
    }

    private func handleError(_ error: Error) { errorMessage = error.localizedDescription }
    func clearMessages() { errorMessage = nil; successMessage = nil }
}
