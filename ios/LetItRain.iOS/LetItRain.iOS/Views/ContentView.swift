// Views/ContentView.swift
// Root view. Gates on authentication state.

import SwiftUI

struct ContentView: View {

    @EnvironmentObject var authVM:            AuthViewModel
    @EnvironmentObject var connectionManager: ConnectionManager

    @StateObject private var firebaseRepo = FirebaseRepository()
    @StateObject private var deviceVM:      DeviceViewModel

    init(connectionManager: ConnectionManager) {
        // DeviceViewModel needs both dependencies. We create the repo here and
        // reuse the app-wide ConnectionManager (injected from LetItRainApp) so
        // there's only one instance — the same one that gets `metaProvider`
        // wired up below and that HomeView/DashboardView read via
        // @EnvironmentObject.
        let repo = FirebaseRepository()
        _deviceVM      = StateObject(wrappedValue: DeviceViewModel(connectionManager: connectionManager, firebaseRepository: repo))
        _firebaseRepo  = StateObject(wrappedValue: repo)
    }

    var body: some View {
        Group {
            if !authVM.isSignedIn {
                LoginView()
            } else if authVM.isResolvingDevice {
                ProgressView("Loading your device…")
            } else if authVM.deviceID == nil {
                // Resolution finished but users/{uid}/device_id was empty --
                // not a loading state, so don't spin forever. AuthViewModel
                // already set errorMessage explaining this ("contact whoever
                // set up this project"); offer a way out rather than
                // stranding the user on a dead screen.
                VStack(spacing: 16) {
                    Text(authVM.errorMessage ?? "Your account isn't assigned to a device yet.")
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.secondary)
                    Button("Sign Out", role: .destructive) { authVM.signOut() }
                }
                .padding()
            } else if let deviceID = authVM.deviceID {
                HomeView()
                    .environmentObject(deviceVM)
                    .environmentObject(firebaseRepo)
                    .task(id: deviceID) {
                        firebaseRepo.configure(deviceID: deviceID)
                        // Wire meta provider so ConnectionManager can read the Pico's IP
                        connectionManager.metaProvider = { [weak firebaseRepo] in
                            await firebaseRepo?.currentMeta()
                        }
                        firebaseRepo.startListening()
                        connectionManager.evaluate(reason: "app launch")
                    }
            }
        }
        .onChange(of: authVM.isSignedIn) { _, signedIn in
            if !signedIn {
                firebaseRepo.reset()
            }
        }
        .animation(.easeInOut(duration: 0.25), value: authVM.isSignedIn)
    }
}
