// Views/DashboardView.swift
// Main control screen. Shows status, manual controls (local only),
// skip-today (both modes), and device info.

import SwiftUI

struct DashboardView: View {

    @EnvironmentObject var connectionManager: ConnectionManager
    @EnvironmentObject var deviceVM:          DeviceViewModel

    @State private var selectedDuration:  Int  = 10
    @State private var showSkipConfirm:   Bool = false
    @State private var showCancelConfirm: Bool = false

    private let durationOptions = [5, 10, 15, 20, 30, 45, 60]

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {
                // Offline warning
                if !deviceVM.status.isRecentlyOnline {
                    offlineBanner
                }

                // Skip active banner
                if deviceVM.status.activeSkip {
                    skipActiveBanner
                }

                // Status card
                statusCard

                // Manual control (local only)
                if connectionManager.mode.isLocal {
                    manualControlCard
                } else {
                    remoteOnlyNotice
                }

                // Skip today card
                skipCard

                // Device info
                deviceInfoCard
            }
            .padding()
        }
        .background(Color(hex: "0A1628").ignoresSafeArea())
        .navigationBarHidden(true)
        // Error / success toasts
        .overlay(alignment: .top) {
            if let msg = deviceVM.errorMessage {
                ToastView(message: msg, style: .error)
                    .transition(.move(edge: .top).combined(with: .opacity))
                    .onAppear { DispatchQueue.main.asyncAfter(deadline: .now() + 3) { deviceVM.clearMessages() } }
            } else if let msg = deviceVM.successMessage {
                ToastView(message: msg, style: .success)
                    .transition(.move(edge: .top).combined(with: .opacity))
                    .onAppear { DispatchQueue.main.asyncAfter(deadline: .now() + 2) { deviceVM.clearMessages() } }
            }
        }
        .animation(.easeInOut(duration: 0.3), value: deviceVM.errorMessage)
        .animation(.easeInOut(duration: 0.3), value: deviceVM.successMessage)
        .onAppear {
            selectedDuration = deviceVM.config?.manualDefaultDurationMinutes ?? 10
        }
        .onChange(of: deviceVM.config?.manualDefaultDurationMinutes) { _, newVal in
            if let v = newVal { selectedDuration = v }
        }
        .confirmationDialog(
            "Skip today's scheduled run?",
            isPresented:    $showSkipConfirm,
            titleVisibility: .visible
        ) {
            Button("Skip Today", role: .destructive) { deviceVM.skipToday() }
            Button("Cancel",     role: .cancel) {}
        } message: {
            Text("The Pico will receive this within 60 seconds and skip its next scheduled run.")
        }
        .confirmationDialog(
            "Cancel the skip override?",
            isPresented:    $showCancelConfirm,
            titleVisibility: .visible
        ) {
            Button("Cancel Skip", role: .destructive) { deviceVM.cancelSkip() }
            Button("Keep Skip",   role: .cancel) {}
        }
    }

    // MARK: - Offline banner

    private var offlineBanner: some View {
        HStack(spacing: 10) {
            Image(systemName: "exclamationmark.wifi")
                .foregroundColor(Color(hex: "FF6B6B"))
            VStack(alignment: .leading, spacing: 2) {
                Text("Device Offline")
                    .font(.footnote.weight(.semibold))
                    .foregroundColor(Color(hex: "FF6B6B"))
                Text(lastSeenText)
                    .font(.caption2)
                    .foregroundColor(.white.opacity(0.5))
            }
            Spacer()
        }
        .padding()
        .background(Color(hex: "FF6B6B").opacity(0.12))
        .cornerRadius(12)
    }

    private var lastSeenText: String {
        let elapsed = Date().timeIntervalSince1970 - deviceVM.status.lastHeartbeat
        if elapsed < 60  { return "Last seen \(Int(elapsed))s ago" }
        if elapsed < 3600 { return "Last seen \(Int(elapsed / 60))m ago" }
        return "Last seen \(Int(elapsed / 3600))h ago"
    }

    // MARK: - Skip active banner

    private var skipActiveBanner: some View {
        HStack(spacing: 10) {
            Image(systemName: "calendar.badge.minus")
                .foregroundColor(Color(hex: "FFA726"))
            VStack(alignment: .leading, spacing: 2) {
                Text("Today's scheduled run is skipped")
                    .font(.footnote.weight(.semibold))
                    .foregroundColor(Color(hex: "FFA726"))
                Text(skipReasonText)
                    .font(.caption2)
                    .foregroundColor(.white.opacity(0.5))
            }
            Spacer()
        }
        .padding()
        .background(Color(hex: "FFA726").opacity(0.12))
        .cornerRadius(12)
    }

    private var skipReasonText: String {
        switch deviceVM.status.activeSkipReason {
        case "rain":         return "Skipped due to rainfall"
        case "manual_local": return "Manually skipped from local app"
        case "manual_remote": return "Manually skipped remotely"
        default:             return "Skip override active"
        }
    }

    // MARK: - Status card

    private var statusCard: some View {
        VStack(spacing: 20) {
            // Animated status indicator
            ZStack {
                if deviceVM.status.isRunning {
                    // Pulsing rings
                    ForEach(0..<3) { i in
                        Circle()
                            .stroke(Color(hex: "42A5F5").opacity(0.3), lineWidth: 2)
                            .frame(width: CGFloat(80 + i * 24), height: CGFloat(80 + i * 24))
                            .scaleEffect(deviceVM.status.isRunning ? 1.2 : 1.0)
                            .opacity(deviceVM.status.isRunning ? 0 : 1)
                            .animation(
                                .easeOut(duration: 1.5)
                                    .repeatForever(autoreverses: false)
                                    .delay(Double(i) * 0.4),
                                value: deviceVM.status.isRunning
                            )
                    }
                }

                Circle()
                    .fill(
                        deviceVM.status.isRunning
                            ? LinearGradient(colors: [Color(hex: "1565C0"), Color(hex: "42A5F5")],
                                             startPoint: .topLeading, endPoint: .bottomTrailing)
                            : LinearGradient(colors: [Color(hex: "1E2A3A"), Color(hex: "263545")],
                                             startPoint: .topLeading, endPoint: .bottomTrailing)
                    )
                    .frame(width: 80, height: 80)

                Image(systemName: deviceVM.status.isRunning ? "drop.fill" : "drop")
                    .font(.system(size: 32))
                    .foregroundColor(deviceVM.status.isRunning ? .white : .white.opacity(0.4))
            }

            // Status text
            VStack(spacing: 4) {
                Text(deviceVM.status.isRunning ? "Running · Zone 1" : "Idle · Zone 1")
                    .font(.title2.weight(.semibold))
                    .foregroundColor(.white)

                if deviceVM.status.isRunning {
                    // Live countdown
                    TimelineView(.periodic(from: .now, by: 1)) { _ in
                        Text(countdownText)
                            .font(.headline.monospacedDigit())
                            .foregroundColor(Color(hex: "64B5F6"))
                    }

                    // Progress bar
                    if let progress = deviceVM.status.runProgress {
                        ProgressView(value: progress)
                            .tint(Color(hex: "42A5F5"))
                            .frame(width: 200)
                    }
                }

                // Last run info
                if let lastStart = deviceVM.status.lastRunStart {
                    Text(lastRunSummary(lastStart))
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.45))
                }
            }
        }
        .padding(24)
        .frame(maxWidth: .infinity)
        .background(Color(hex: "0F2038"))
        .cornerRadius(16)
    }

    private var countdownText: String {
        guard let remaining = deviceVM.status.remainingSeconds else { return "--:--" }
        let minutes = Int(remaining) / 60
        let seconds = Int(remaining) % 60
        return String(format: "Stops in %d:%02d", minutes, seconds)
    }

    private func lastRunSummary(_ startEpoch: TimeInterval) -> String {
        let date = Date(timeIntervalSince1970: startEpoch)
        let formatter = DateFormatter()
        formatter.dateFormat = "EEE MMM d · h:mm a"
        let mode     = deviceVM.status.lastRunMode ?? ""
        let status   = deviceVM.status.lastRunStatus ?? ""
        var duration = ""
        if let end = deviceVM.status.lastRunEnd {
            let mins = Int((end - startEpoch) / 60)
            duration = " · \(mins) min"
        }
        return "Last run: \(formatter.string(from: date))\(duration) · \(mode) · \(status)"
    }

    // MARK: - Manual control card

    private var manualControlCard: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Manual Control")
                .font(.footnote.weight(.semibold))
                .foregroundColor(.white.opacity(0.5))
                .textCase(.uppercase)
                .tracking(0.5)

            // Duration chips
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(durationOptions, id: \.self) { mins in
                        Button {
                            selectedDuration = mins
                        } label: {
                            Text("\(mins) min")
                                .font(.subheadline.weight(selectedDuration == mins ? .semibold : .regular))
                                .foregroundColor(selectedDuration == mins ? .white : .white.opacity(0.5))
                                .padding(.horizontal, 16)
                                .padding(.vertical, 8)
                                .background(
                                    selectedDuration == mins
                                        ? Color(hex: "1565C0")
                                        : Color(hex: "1E2A3A")
                                )
                                .cornerRadius(20)
                        }
                    }
                }
            }

            // Start / Stop buttons
            if deviceVM.status.isRunning {
                Button {
                    deviceVM.stop()
                } label: {
                    Label("Stop Zone 1", systemImage: "stop.fill")
                        .font(.headline)
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(Color(hex: "C62828"))
                        .cornerRadius(12)
                }
                .disabled(deviceVM.isLoading)
            } else {
                Button {
                    deviceVM.startManual(durationMinutes: selectedDuration)
                } label: {
                    Label("Start Zone 1", systemImage: "play.fill")
                        .font(.headline)
                        .foregroundColor(.white)
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(
                            deviceVM.status.isRecentlyOnline
                                ? LinearGradient(colors: [Color(hex: "1565C0"), Color(hex: "0D47A1")],
                                                 startPoint: .leading, endPoint: .trailing)
                                : LinearGradient(colors: [Color(hex: "333"), Color(hex: "333")],
                                                 startPoint: .leading, endPoint: .trailing)
                        )
                        .cornerRadius(12)
                }
                .disabled(!deviceVM.status.isRecentlyOnline || deviceVM.isLoading)
            }
        }
        .padding()
        .background(Color(hex: "0F2038"))
        .cornerRadius(16)
    }

    // MARK: - Remote-only notice

    private var remoteOnlyNotice: some View {
        HStack(spacing: 12) {
            Image(systemName: "wifi")
                .foregroundColor(.white.opacity(0.3))
            Text("Connect to your home Wi-Fi to manually control the sprinkler.")
                .font(.subheadline)
                .foregroundColor(.white.opacity(0.4))
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(hex: "0F2038"))
        .cornerRadius(16)
    }

    // MARK: - Skip card

    @ViewBuilder
    private var skipCard: some View {
        // Only show if schedule is enabled (or we don't have config — remote mode)
        let scheduleEnabled = deviceVM.config?.schedule.enabled ?? true
        if scheduleEnabled {
            VStack(alignment: .leading, spacing: 12) {
                Text("Scheduled Run")
                    .font(.footnote.weight(.semibold))
                    .foregroundColor(.white.opacity(0.5))
                    .textCase(.uppercase)
                    .tracking(0.5)

                if deviceVM.status.activeSkip {
                    Button {
                        showCancelConfirm = true
                    } label: {
                        Label("Cancel Today's Skip", systemImage: "arrow.counterclockwise")
                            .font(.subheadline.weight(.medium))
                            .foregroundColor(Color(hex: "FFA726"))
                            .frame(maxWidth: .infinity)
                            .padding()
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(Color(hex: "FFA726").opacity(0.5), lineWidth: 1)
                            )
                    }
                } else {
                    Button {
                        showSkipConfirm = true
                    } label: {
                        Label("Skip Today's Run", systemImage: "calendar.badge.minus")
                            .font(.subheadline.weight(.medium))
                            .foregroundColor(Color(hex: "FFA726"))
                            .frame(maxWidth: .infinity)
                            .padding()
                            .overlay(
                                RoundedRectangle(cornerRadius: 12)
                                    .stroke(Color(hex: "FFA726").opacity(0.5), lineWidth: 1)
                            )
                    }
                }
            }
            .padding()
            .background(Color(hex: "0F2038"))
            .cornerRadius(16)
        }
    }

    // MARK: - Device info card

    private var deviceInfoCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Device Info")
                .font(.footnote.weight(.semibold))
                .foregroundColor(.white.opacity(0.5))
                .textCase(.uppercase)
                .tracking(0.5)

            infoRow("Firmware",   value: deviceVM.status.firmwareVersion ?? "—")
            infoRow("Heartbeat",  value: lastSeenText)
            if let config = deviceVM.config {
                infoRow("Schedule",
                        value: config.schedule.enabled
                            ? "\(config.schedule.dayAbbreviations.joined(separator: ", ")) · \(config.schedule.startTimeString)"
                            : "Disabled")
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(hex: "0F2038"))
        .cornerRadius(16)
    }

    private func infoRow(_ label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(.subheadline)
                .foregroundColor(.white.opacity(0.5))
            Spacer()
            Text(value)
                .font(.subheadline)
                .foregroundColor(.white.opacity(0.85))
        }
    }
}

// MARK: - Toast

struct ToastView: View {
    enum ToastStyle { case success, error }
    let message: String
    let style:   ToastStyle

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: style == .success ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                .foregroundColor(style == .success ? Color(hex: "66BB6A") : Color(hex: "FF6B6B"))
            Text(message)
                .font(.subheadline)
                .foregroundColor(.white)
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 12)
        .background(Color(hex: "1E2A3A"))
        .cornerRadius(24)
        .shadow(color: .black.opacity(0.3), radius: 8, y: 4)
        .padding(.top, 12)
    }
}

#Preview {
    DashboardView()
        .environmentObject(ConnectionManager())
        .environmentObject(DeviceViewModel(
            connectionManager: ConnectionManager(),
            firebaseRepository: FirebaseRepository()
        ))
}
