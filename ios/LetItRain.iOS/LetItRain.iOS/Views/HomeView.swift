// Views/HomeView.swift
// Root tab view shown after sign-in.
// Contains Dashboard and Schedule tabs.
// Shows a mode indicator pill at the top of every screen.

import SwiftUI

struct HomeView: View {

    @EnvironmentObject var authVM:            AuthViewModel
    @EnvironmentObject var connectionManager: ConnectionManager
    @EnvironmentObject var deviceVM:          DeviceViewModel

    @State private var selectedTab = 0

    var body: some View {
        VStack(spacing: 0) {
            // Mode indicator banner — always visible
            modeBanner

            TabView(selection: $selectedTab) {
                DashboardView()
                    .tabItem {
                        Label("Dashboard", systemImage: "drop.fill")
                    }
                    .tag(0)

                scheduleTab
                    .tabItem {
                        Label("Schedule", systemImage: "calendar")
                    }
                    .tag(1)
            }
        }
        .background(Color(hex: "0A1628").ignoresSafeArea())
        .onAppear {
            deviceVM.refresh()
        }
    }

    // MARK: - Mode banner

    private var modeBanner: some View {
        HStack {
            Spacer()
            HStack(spacing: 6) {
                Circle()
                    .fill(modeColor)
                    .frame(width: 7, height: 7)
                    .opacity(connectionManager.mode == .offline ? 0.5 : 1)

                Text(connectionManager.mode.displayName)
                    .font(.caption2.weight(.semibold))
                    .foregroundColor(modeColor)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 5)
            .background(modeColor.opacity(0.12))
            .clipShape(Capsule())

            // Sign out button
            Button {
                authVM.signOut()
            } label: {
                Image(systemName: "rectangle.portrait.and.arrow.right")
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.4))
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .background(Color(hex: "0A1628"))
    }

    private var modeColor: Color {
        switch connectionManager.mode {
        case .local:   return Color(hex: "66BB6A")   // green
        case .remote:  return Color(hex: "FFA726")   // amber
        case .offline: return .gray
        }
    }

    // MARK: - Schedule tab (disabled in remote mode)

    @ViewBuilder
    private var scheduleTab: some View {
        if connectionManager.mode.isLocal {
            ScheduleView()
        } else {
            VStack(spacing: 16) {
                Spacer()
                Image(systemName: "wifi.slash")
                    .font(.system(size: 44))
                    .foregroundColor(.white.opacity(0.3))
                Text("Schedule editing requires\na local network connection.")
                    .font(.subheadline)
                    .foregroundColor(.white.opacity(0.5))
                    .multilineTextAlignment(.center)
                Spacer()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(hex: "0A1628"))
        }
    }
}
