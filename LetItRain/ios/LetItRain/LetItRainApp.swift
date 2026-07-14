// LetItRainApp.swift
// App entry point. Configures Firebase and injects shared environment objects.

import SwiftUI
import FirebaseCore
import UserNotifications

@main
struct LetItRainApp: App {

    @StateObject private var authVM             = AuthViewModel()
    @StateObject private var connectionManager  = ConnectionManager()

    init() {
        FirebaseApp.configure()
        requestNotificationPermission()
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(authVM)
                .environmentObject(connectionManager)
        }
    }

    // MARK: - Push Notifications

    private func requestNotificationPermission() {
        UNUserNotificationCenter.current().requestAuthorization(
            options: [.alert, .sound, .badge]
        ) { granted, error in
            if let error {
                print("Notification permission error:", error)
            } else {
                print("Notification permission granted:", granted)
            }
            if granted {
                DispatchQueue.main.async {
                    UIApplication.shared.registerForRemoteNotifications()
                }
            }
        }
    }
}
