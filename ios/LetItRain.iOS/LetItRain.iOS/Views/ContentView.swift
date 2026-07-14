// Views/ContentView.swift
// Root view. Gates on authentication state.

import SwiftUI

struct ContentView: View {

    @EnvironmentObject var authVM:            AuthViewModel
    @EnvironmentObject var connectionManager: ConnectionManager

    @StateObject private var firebaseRepo = FirebaseRepository()
    @StateObject private var deviceVM:      DeviceViewModel

    init() {
        // DeviceViewModel needs both dependencies. We create them here so
        // they share the same instances throughout the app.
        let repo = FirebaseRepository()
        let cm   = ConnectionManager()
        _deviceVM      = StateObject(wrappedValue: DeviceViewModel(connectionManager: cm, firebaseRepository: repo))
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
