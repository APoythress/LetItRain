// ViewModels/DeviceViewModel.swift
// Unified ViewModel that sits above both data layers (Firebase + local HTTP).
// Views always talk to this ViewModel — never directly to the data layers.
// Mode switching is transparent to the views.

import Foundation
import Combine

@MainActor
final class DeviceViewModel: ObservableObject {

    // MARK: - Published state

    @Published var status:       DeviceStatus  = .placeholder
    @Published var config:       DeviceConfig? = nil     // nil in remote mode
    @Published var isLoading:    Bool          = false
    @Published var errorMessage: String?       = nil
    @Published var successMessage: String?     = nil

    // MARK: - Dependencies

    private let connectionManager:  ConnectionManager
    private let firebaseRepository: FirebaseRepository
    private var localClient:        LocalAPIClient?

    private var cancellables = Set<AnyCancellable>()
    private var localRefreshTimer: Timer?

    // MARK: - Init

    init(connectionManager: ConnectionManager, firebaseRepository: FirebaseRepository) {
        self.connectionManager  = connectionManager
        self.firebaseRepository = firebaseRepository

        observeModeChanges()
        observeFirebaseStatus()
    }

    // MARK: - Mode observation

    private func observeModeChanges() {
        connectionManager.$mode
            .receive(on: DispatchQueue.main)
            .sink { [weak self] newMode in
                self?.handleModeChange(newMode)
            }
            .store(in: &cancellables)
    }

    private func handleModeChange(_ newMode: AppConnectionMode) {
        switch newMode {
        case .local(let baseURL):
            localClient = LocalAPIClient(baseURL: baseURL)
            startLocalPolling()
            // Don't stop Firebase — still want meta/IP updates
        case .remote, .offline:
            localClient = nil
            stopLocalPolling()
            config = nil  // config not available remotely
        }
    }

    // MARK: - Firebase status passthrough

    private func observeFirebaseStatus() {
        firebaseRepository.$status
            .receive(on: DispatchQueue.main)
            .sink { [weak self] fbStatus in
                // Only use Firebase status when in remote/offline mode
                guard let self else { return }
                if !self.connectionManager.mode.isLocal {
                    self.status = fbStatus
                }
            }
            .store(in: &cancellables)
    }

    // MARK: - Local polling (replaces Firebase in local mode)

    private func startLocalPolling() {
        stopLocalPolling()
        // Poll every 3 seconds for snappy UI in local mode
        localRefreshTimer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in
            Task { @MainActor [weak self] in
                await self?.refreshLocalStatus()
            }
        }
        // Immediate first fetch
        Task { await refreshLocalStatus() }
    }

    private func stopLocalPolling() {
        localRefreshTimer?.invalidate()
        localRefreshTimer = nil
    }

    private func refreshLocalStatus() async {
        guard let client = localClient else { return }
        do {
            let newStatus = try await client.fetchStatus()
            status = newStatus
        } catch {
            // On failure, trigger a mode re-evaluation (Pico may have rebooted)
            connectionManager.evaluate()
        }
    }

    // MARK: - Public actions

    /// Refresh status and config (in local mode also fetches config).
    func refresh() {
        Task {
            isLoading = true
            defer { isLoading = false }

            if let client = localClient {
                async let statusTask = client.fetchStatus()
                async let configTask = client.fetchConfig()
                do {
                    let (s, c) = try await (statusTask, configTask)
                    status = s
                    config = c
                } catch {
                    handleError(error)
                    connectionManager.evaluate()
                }
            }
            // In remote mode, Firebase listener handles status — no manual fetch needed
        }
    }

    /// Start a manual run. Local mode only.
    func startManual(durationMinutes: Int) {
        guard let client = localClient else {
            errorMessage = "Manual control requires a local network connection."
            return
        }
        Task {
            isLoading = true
            do {
                try await client.sendStart(durationMinutes: durationMinutes)
                await refreshLocalStatus()
            } catch {
                handleError(error)
            }
            isLoading = false
        }
    }

    /// Stop the current run. Local mode only.
    func stop() {
        guard let client = localClient else {
            errorMessage = "Stop control requires a local network connection."
            return
        }
        Task {
            isLoading = true
            do {
                try await client.sendStop()
                await refreshLocalStatus()
            } catch {
                handleError(error)
            }
            isLoading = false
        }
    }

    /// Skip today's scheduled run. Available in both modes.
    func skipToday() {
        Task {
            isLoading = true
            do {
                if let client = localClient {
                    try await client.sendSkipToday()
                    await refreshLocalStatus()
                } else {
                    try await firebaseRepository.writeSkipToday()
                }
                successMessage = "Today's scheduled run will be skipped."
            } catch {
                handleError(error)
            }
            isLoading = false
        }
    }

    /// Cancel a previously set skip. Available in both modes.
    func cancelSkip() {
        Task {
            isLoading = true
            do {
                if let client = localClient {
                    try await client.cancelSkip()
                    await refreshLocalStatus()
                } else {
                    try await firebaseRepository.cancelSkip()
                }
                successMessage = "Skip cancelled. Scheduled run will proceed."
            } catch {
                handleError(error)
            }
            isLoading = false
        }
    }

    /// Update the device config. Local mode only.
    func updateConfig(_ newConfig: DeviceConfig) {
        guard let client = localClient else {
            errorMessage = "Config changes require a local network connection."
            return
        }
        Task {
            isLoading = true
            do {
                try await client.updateConfig(newConfig)
                config = newConfig
                successMessage = "Settings saved."
            } catch {
                handleError(error)
            }
            isLoading = false
        }
    }

    // MARK: - Error handling

    private func handleError(_ error: Error) {
        errorMessage = error.localizedDescription
    }

    func clearMessages() {
        errorMessage   = nil
        successMessage = nil
    }
}
