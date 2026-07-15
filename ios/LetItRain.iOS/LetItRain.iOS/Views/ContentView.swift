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
            if authVM.isSignedIn {
                HomeView()
                    .environmentObject(deviceVM)
                    .environmentObject(firebaseRepo)
                    .task {
                        // Wire meta provider so ConnectionManager can read the Pico's IP
                        connectionManager.metaProvider = { [weak firebaseRepo] in
                            await firebaseRepo?.currentMeta()
                        }
                        firebaseRepo.startListening()
                        connectionManager.evaluate()
                    }
            } else {
                LoginView()
            }
        }
        .animation(.easeInOut(duration: 0.25), value: authVM.isSignedIn)
    }
}
