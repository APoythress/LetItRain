// ViewModels/DeviceViewModel.swift
// Unified ViewModel. Mode-aware. Delegates schedule logic to ScheduleViewModel.

import Foundation
import Combine

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

    private func wireScheduleVM() {
        scheduleVM.onSave = { [weak self] updatedConfig in
            guard let self else { return }
            if let client = self.localClient {
                try await client.updateConfig(updatedConfig)
                self.config = updatedConfig
            } else {
                try await self.firebaseRepository.writeConfig(updatedConfig)
            }
        }
    }

    // MARK: - Local polling

    private func startLocalPolling() {
        stopLocalPolling()
        localRefreshTimer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in
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
            async let s = client.fetchStatus()
            async let c = client.fetchConfig()
            let (newStatus, newConfig) = try await (s, c)
            status = newStatus
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

    func skipToday() {
        Task {
            isLoading = true
            do {
                if let client = localClient {
                    try await client.sendSkipToday()
                    await refreshLocal()
                } else {
                    try await firebaseRepository.writeSkipToday()
                }
                successMessage = "Today's scheduled run will be skipped."
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
