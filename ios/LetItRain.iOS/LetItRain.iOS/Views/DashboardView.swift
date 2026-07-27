// Views/DashboardView.swift
// Main control screen. Multi-zone aware.
// Local mode: zone selector + start/stop per zone, instant single-day skip.
// Remote mode: read-only status (last run, last synced) + skip-for-N-days.

import SwiftUI

struct DashboardView: View {

    @EnvironmentObject var connectionManager: ConnectionManager
    @EnvironmentObject var deviceVM:          DeviceViewModel

    @State private var selectedZone:     Int  = 1
    @State private var selectedDuration: Int  = 10
    @State private var selectedSkipDays: Int  = 3
    @State private var showSkipConfirm  = false
    @State private var showCancelConfirm = false

    private let durationOptions = [5, 10, 15, 20, 30, 45, 60]
    private let skipDayOptions  = [1, 2, 3, 5, 7, 14]

    private var enabledZones: [ZoneConfig] {
        deviceVM.config?.enabledZones ?? []
    }

    private var activeZoneName: String {
        guard let id = deviceVM.status.activeZoneId else { return "Zone" }
        return deviceVM.config?.zones.first { $0.id == id }?.name ?? "Zone \(id)"
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 16) {

                if !deviceVM.status.isRecentlyOnline { offlineBanner }
                if deviceVM.status.activeSkip        { skipActiveBanner }

                statusCard

                if connectionManager.mode.isLocal {
                    if !enabledZones.isEmpty { manualControlCard }
                } else {
                    remoteNotice
                }

                skipCard
                deviceInfoCard
            }
            .padding()
        }
        .background(Color(hex: "0A1628").ignoresSafeArea())
        .overlay(alignment: .top) { toastOverlay }
        .animation(.easeInOut(duration: 0.3), value: deviceVM.errorMessage)
        .animation(.easeInOut(duration: 0.3), value: deviceVM.successMessage)
        .onAppear {
            selectedZone     = enabledZones.first?.id ?? 1
            selectedDuration = deviceVM.config?.manualDefaultDurationMinutes ?? 10
        }
        .onChange(of: deviceVM.config) { _, cfg in
            selectedDuration = cfg?.manualDefaultDurationMinutes ?? 10
            if let first = cfg?.enabledZones.first { selectedZone = first.id }
        }
        .confirmationDialog(skipConfirmTitle,
                            isPresented: $showSkipConfirm, titleVisibility: .visible) {
            Button(skipConfirmButtonLabel, role: .destructive) {
                if connectionManager.mode.isLocal {
                    deviceVM.skipToday()
                } else {
                    deviceVM.skipForDays(selectedSkipDays)
                }
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text(connectionManager.mode.isLocal
                 ? "The controller will receive this within 60 seconds."
                 : "May take up to an hour to reach the device.")
        }
        .confirmationDialog("Cancel the skip?",
                            isPresented: $showCancelConfirm, titleVisibility: .visible) {
            Button("Cancel Skip", role: .destructive) { deviceVM.cancelSkip() }
            Button("Keep Skip",   role: .cancel) {}
        }
    }

    // MARK: - Offline banner

    private var offlineBanner: some View {
        HStack(spacing: 10) {
            Image(systemName: "wifi.slash").foregroundColor(Color(hex: "FF6B6B"))
            VStack(alignment: .leading, spacing: 2) {
                Text("Device Offline").font(.footnote.weight(.semibold)).foregroundColor(Color(hex: "FF6B6B"))
                Text(lastSeenText).font(.caption2).foregroundColor(.white.opacity(0.5))
            }
            Spacer()
        }
        .padding().background(Color(hex: "FF6B6B").opacity(0.12)).cornerRadius(12)
    }

    private var lastSeenText: String {
        "Last seen \(syncedAgoText)"
    }

    private var syncedAgoText: String {
        let e = Date().timeIntervalSince1970 - deviceVM.status.lastSyncedEpoch
        if e < 60    { return "\(Int(e))s ago" }
        if e < 3600  { return "\(Int(e/60))m ago" }
        return "\(Int(e/3600))h ago"
    }

    // MARK: - Skip active banner

    private var skipActiveBanner: some View {
        HStack(spacing: 10) {
            Image(systemName: "calendar.badge.minus").foregroundColor(Color(hex: "FFA726"))
            VStack(alignment: .leading, spacing: 2) {
                Text("Today's run is skipped").font(.footnote.weight(.semibold)).foregroundColor(Color(hex: "FFA726"))
                Text(skipReasonText).font(.caption2).foregroundColor(.white.opacity(0.5))
            }
            Spacer()
        }
        .padding().background(Color(hex: "FFA726").opacity(0.12)).cornerRadius(12)
    }

    private var skipReasonText: String {
        switch deviceVM.status.activeSkipReason {
        case "rain":          return "Skipped due to rainfall"
        case "manual_local":  return "Skipped from local app"
        case "manual_remote": return "Skipped remotely"
        default:              return "Override active"
        }
    }

    // MARK: - Status card

    private var statusCard: some View {
        VStack(spacing: 20) {

            // Animated indicator
            ZStack {
                if deviceVM.status.isRunning {
                    ForEach(0..<3) { i in
                        Circle()
                            .stroke(Color(hex: "42A5F5").opacity(0.25), lineWidth: 2)
                            .frame(width: CGFloat(80 + i * 26), height: CGFloat(80 + i * 26))
                            .scaleEffect(1.2).opacity(0)
                            .animation(.easeOut(duration: 1.5)
                                .repeatForever(autoreverses: false).delay(Double(i) * 0.4),
                                       value: deviceVM.status.isRunning)
                    }
                }
                Circle()
                    .fill(deviceVM.status.isRunning
                          ? LinearGradient(colors: [Color(hex: "1565C0"), Color(hex: "42A5F5")],
                                           startPoint: .topLeading, endPoint: .bottomTrailing)
                          : LinearGradient(colors: [Color(hex: "1E2A3A"), Color(hex: "263545")],
                                           startPoint: .topLeading, endPoint: .bottomTrailing))
                    .frame(width: 80, height: 80)
                Image(systemName: deviceVM.status.isRunning ? "drop.fill" : "drop")
                    .font(.system(size: 30))
                    .foregroundColor(deviceVM.status.isRunning ? .white : .white.opacity(0.3))
            }

            // Status text
            VStack(spacing: 6) {
                if deviceVM.status.isRunning {
                    Text("Running · \(activeZoneName)")
                        .font(.title2.weight(.semibold)).foregroundColor(.white)
                    TimelineView(.periodic(from: .now, by: 1)) { _ in
                        Text(countdownText)
                            .font(.headline.monospacedDigit()).foregroundColor(Color(hex: "64B5F6"))
                    }
                    if let progress = deviceVM.status.runProgress {
                        ProgressView(value: progress).tint(Color(hex: "42A5F5")).frame(width: 200)
                    }
                } else {
                    Text("Idle").font(.title2.weight(.semibold)).foregroundColor(.white)
                    if let lastStart = deviceVM.status.lastRunStart {
                        Text(lastRunSummary(lastStart))
                            .font(.caption).foregroundColor(.white.opacity(0.4))
                    }
                }
            }
        }
        .padding(24).frame(maxWidth: .infinity)
        .background(Color(hex: "0F2038")).cornerRadius(16)
    }

    private var countdownText: String {
        guard let r = deviceVM.status.remainingSeconds else { return "--:--" }
        return String(format: "Stops in %d:%02d", Int(r)/60, Int(r)%60)
    }

    private func lastRunSummary(_ epoch: TimeInterval) -> String {
        let f = DateFormatter(); f.dateFormat = "EEE MMM d · h:mm a"
        let name = deviceVM.config?.zones.first { $0.id == deviceVM.status.lastRunZoneId }?.name
        let zonePart = name.map { " · \($0)" } ?? ""
        var durPart = ""
        if let end = deviceVM.status.lastRunEnd {
            durPart = " · \(Int((end - epoch) / 60)) min"
        }
        return "Last: \(f.string(from: Date(timeIntervalSince1970: epoch)))\(zonePart)\(durPart)"
    }

    // MARK: - Manual control (local only)

    private var manualControlCard: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Manual Control").font(.footnote.weight(.semibold))
                .foregroundColor(.white.opacity(0.5)).textCase(.uppercase).tracking(0.5)

            // Zone picker
            if enabledZones.count > 1 {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        ForEach(enabledZones) { zone in
                            Button { selectedZone = zone.id } label: {
                                Text(zone.name)
                                    .font(.subheadline.weight(selectedZone == zone.id ? .semibold : .regular))
                                    .foregroundColor(selectedZone == zone.id ? .white : .white.opacity(0.5))
                                    .padding(.horizontal, 14).padding(.vertical, 8)
                                    .background(selectedZone == zone.id ? Color(hex: "1565C0") : Color(hex: "1E2A3A"))
                                    .cornerRadius(20)
                            }
                        }
                    }
                }
            }

            // Duration chips
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(durationOptions, id: \.self) { mins in
                        Button { selectedDuration = mins } label: {
                            Text("\(mins) min")
                                .font(.subheadline.weight(selectedDuration == mins ? .semibold : .regular))
                                .foregroundColor(selectedDuration == mins ? .white : .white.opacity(0.5))
                                .padding(.horizontal, 16).padding(.vertical, 8)
                                .background(selectedDuration == mins ? Color(hex: "1565C0") : Color(hex: "1E2A3A"))
                                .cornerRadius(20)
                        }
                    }
                }
            }

            // Start / Stop
            if deviceVM.status.isRunning {
                Button { deviceVM.stop() } label: {
                    Label("Stop \(activeZoneName)", systemImage: "stop.fill")
                        .font(.headline).foregroundColor(.white)
                        .frame(maxWidth: .infinity).padding()
                        .background(Color(hex: "C62828")).cornerRadius(12)
                }
                .disabled(deviceVM.isLoading)
            } else {
                Button { deviceVM.startManual(zoneId: selectedZone, durationMinutes: selectedDuration) } label: {
                    Label("Start \(enabledZones.first { $0.id == selectedZone }?.name ?? "Zone")", systemImage: "play.fill")
                        .font(.headline).foregroundColor(.white)
                        .frame(maxWidth: .infinity).padding()
                        .background(deviceVM.status.isRecentlyOnline
                                    ? LinearGradient(colors: [Color(hex: "1565C0"), Color(hex: "0D47A1")],
                                                     startPoint: .leading, endPoint: .trailing)
                                    : LinearGradient(colors: [Color(hex: "333"), Color(hex: "333")],
                                                     startPoint: .leading, endPoint: .trailing))
                        .cornerRadius(12)
                }
                .disabled(!deviceVM.status.isRecentlyOnline || deviceVM.isLoading)
            }
        }
        .padding().background(Color(hex: "0F2038")).cornerRadius(16)
    }

    // MARK: - Remote notice

    private var remoteNotice: some View {
        HStack(spacing: 12) {
            Image(systemName: "wifi").foregroundColor(.white.opacity(0.3))
            Text("Connect to your home Wi-Fi for manual zone control.")
                .font(.subheadline).foregroundColor(.white.opacity(0.4))
        }
        .padding().frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(hex: "0F2038")).cornerRadius(16)
    }

    // MARK: - Skip card

    @ViewBuilder
    private var skipCard: some View {
        let hasSchedule = deviceVM.config?.schedule != nil
            ? Weekday.allCases.contains { deviceVM.config!.schedule[$0].enabled }
            : true   // assume schedule exists in remote mode

        if hasSchedule {
            VStack(alignment: .leading, spacing: 12) {
                Text("Scheduled Run").font(.footnote.weight(.semibold))
                    .foregroundColor(.white.opacity(0.5)).textCase(.uppercase).tracking(0.5)

                if deviceVM.status.activeSkip {
                    Button { showCancelConfirm = true } label: {
                        Label("Cancel Skip", systemImage: "arrow.counterclockwise")
                            .font(.subheadline.weight(.medium)).foregroundColor(Color(hex: "FFA726"))
                            .frame(maxWidth: .infinity).padding()
                            .overlay(RoundedRectangle(cornerRadius: 12)
                                .stroke(Color(hex: "FFA726").opacity(0.5), lineWidth: 1))
                    }
                } else if connectionManager.mode.isLocal {
                    Button { showSkipConfirm = true } label: {
                        Label("Skip Today's Run", systemImage: "calendar.badge.minus")
                            .font(.subheadline.weight(.medium)).foregroundColor(Color(hex: "FFA726"))
                            .frame(maxWidth: .infinity).padding()
                            .overlay(RoundedRectangle(cornerRadius: 12)
                                .stroke(Color(hex: "FFA726").opacity(0.5), lineWidth: 1))
                    }
                } else {
                    remoteSkipPicker
                }
            }
            .padding().background(Color(hex: "0F2038")).cornerRadius(16)
        }
    }

    // MARK: - Remote skip-for-N-days (out-of-town override)

    private var remoteSkipPicker: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Skip the schedule while you're away:")
                .font(.caption).foregroundColor(.white.opacity(0.5))
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(skipDayOptions, id: \.self) { days in
                        Button { selectedSkipDays = days } label: {
                            Text(days == 1 ? "1 day" : "\(days) days")
                                .font(.subheadline.weight(selectedSkipDays == days ? .semibold : .regular))
                                .foregroundColor(selectedSkipDays == days ? .white : .white.opacity(0.5))
                                .padding(.horizontal, 14).padding(.vertical, 8)
                                .background(selectedSkipDays == days ? Color(hex: "FFA726") : Color(hex: "1E2A3A"))
                                .cornerRadius(20)
                        }
                    }
                }
            }
            Button { showSkipConfirm = true } label: {
                Label(skipConfirmButtonLabel, systemImage: "calendar.badge.minus")
                    .font(.subheadline.weight(.medium)).foregroundColor(Color(hex: "FFA726"))
                    .frame(maxWidth: .infinity).padding()
                    .overlay(RoundedRectangle(cornerRadius: 12)
                        .stroke(Color(hex: "FFA726").opacity(0.5), lineWidth: 1))
            }
        }
    }

    private var skipConfirmTitle: String {
        connectionManager.mode.isLocal
            ? "Skip today's scheduled run?"
            : "Skip the schedule for \(selectedSkipDays) day\(selectedSkipDays == 1 ? "" : "s")?"
    }

    private var skipConfirmButtonLabel: String {
        connectionManager.mode.isLocal
            ? "Skip Today"
            : "Skip \(selectedSkipDays) Day\(selectedSkipDays == 1 ? "" : "s")"
    }

    // MARK: - Device info

    private var deviceInfoCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Device Info").font(.footnote.weight(.semibold))
                .foregroundColor(.white.opacity(0.5)).textCase(.uppercase).tracking(0.5)

            infoRow("Firmware",    value: deviceVM.status.firmwareVersion ?? "—")
            infoRow("Last Synced", value: syncedAgoText)

            if let zones = deviceVM.config?.enabledZones, !zones.isEmpty {
                infoRow("Zones", value: zones.map(\.name).joined(separator: ", "))
            }

            updateRow
            if connectionManager.mode.isLocal { resyncTimeRow }
        }
        .padding().frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(hex: "0F2038")).cornerRadius(16)
    }

    // MARK: - Clock resync row (local only -- the daily 3am job covers remote)

    private var resyncTimeRow: some View {
        HStack {
            Text("Clock drifted?").font(.subheadline).foregroundColor(.white.opacity(0.5))
            Spacer()
            Button {
                deviceVM.resyncTime()
            } label: {
                Text("Resync Time").font(.caption.weight(.semibold))
            }
            .disabled(deviceVM.isLoading)
        }
    }

    // MARK: - OTA update row

    @ViewBuilder
    private var updateRow: some View {
        Divider().background(Color.white.opacity(0.1)).padding(.vertical, 2)

        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("Software Update").font(.subheadline).foregroundColor(.white.opacity(0.5))
                if let message = deviceVM.otaStatus.message, deviceVM.otaStatus.status != "idle" {
                    Text(message).font(.caption2).foregroundColor(.white.opacity(0.4))
                }
            }
            Spacer()
            Button {
                deviceVM.checkForUpdate()
            } label: {
                if deviceVM.otaStatus.isInProgress {
                    ProgressView().tint(.white.opacity(0.6))
                } else {
                    Text("Check Now").font(.caption.weight(.semibold))
                }
            }
            .disabled(deviceVM.otaStatus.isInProgress || !deviceVM.status.isRecentlyOnline)
        }
    }

    private func infoRow(_ label: String, value: String) -> some View {
        HStack {
            Text(label).font(.subheadline).foregroundColor(.white.opacity(0.5))
            Spacer()
            Text(value).font(.subheadline).foregroundColor(.white.opacity(0.85))
        }
    }

    // MARK: - Toast overlay

    @ViewBuilder
    private var toastOverlay: some View {
        if let msg = deviceVM.errorMessage {
            ToastView(message: msg, style: .error).padding(.top, 12)
                .transition(.move(edge: .top).combined(with: .opacity))
                .onAppear { DispatchQueue.main.asyncAfter(deadline: .now()+3) { deviceVM.clearMessages() } }
        } else if let msg = deviceVM.successMessage {
            ToastView(message: msg, style: .success).padding(.top, 12)
                .transition(.move(edge: .top).combined(with: .opacity))
                .onAppear { DispatchQueue.main.asyncAfter(deadline: .now()+2) { deviceVM.clearMessages() } }
        }
    }
}
