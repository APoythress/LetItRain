// LetItRainApp.swift
// App entry point. Configures Firebase and injects shared environment objects.

import SwiftUI
import FirebaseCore

@main
struct LetItRainApp: App {

    @StateObject private var authVM             = AuthViewModel()
    @StateObject private var connectionManager  = ConnectionManager()

    init() {
        FirebaseApp.configure()
    }

    var body: some Scene {
        WindowGroup {
            ContentView(connectionManager: connectionManager)
                .environmentObject(authVM)
                .environmentObject(connectionManager)
        }
    }
}
