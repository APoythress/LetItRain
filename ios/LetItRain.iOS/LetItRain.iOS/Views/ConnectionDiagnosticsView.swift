// Views/ConnectionDiagnosticsView.swift
// On-device trace of local/remote detection — opened by tapping the mode
// badge in HomeView. Exists because the most common real failure (a denied
// "Local Network" permission) fails completely silently otherwise, and the
// developer isn't always attached with a debugger when testing on-device.

import SwiftUI

struct ConnectionDiagnosticsView: View {
    @EnvironmentObject var connectionManager: ConnectionManager
    @Environment(\.dismiss) var dismiss

    var body: some View {
        NavigationView {
            ZStack {
                Color(hex: "0A1628").ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        currentCard
                        if let last = connectionManager.lastDiagnostics {
                            detailCard(last)
                        }
                        historyCard
                    }
                    .padding()
                }
            }
            .navigationTitle("Connection Diagnostics")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }.foregroundColor(.white.opacity(0.6))
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Re-check Now") {
                        connectionManager.evaluate(reason: "manual diagnostics re-check")
                    }
                    .foregroundColor(Color(hex: "64B5F6")).fontWeight(.semibold)
                }
            }
        }
    }

    private var currentCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("CURRENT MODE").font(.caption2.weight(.semibold))
                .foregroundColor(.white.opacity(0.4)).tracking(1)
            HStack {
                Text(connectionManager.mode.displayName)
                    .font(.title2.weight(.bold)).foregroundColor(.white)
                if connectionManager.isEvaluating {
                    ProgressView().tint(.white.opacity(0.6)).padding(.leading, 4)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding().background(Color(hex: "0F2038")).cornerRadius(12)
    }

    @ViewBuilder
    private func detailCard(_ d: ConnectionDiagnostics) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("LAST EVALUATION").font(.caption2.weight(.semibold))
                .foregroundColor(.white.opacity(0.4)).tracking(1)

            row("Triggered by", d.trigger)
            row("Time", d.timestamp.formatted(date: .omitted, time: .standard))
            Divider().background(Color.white.opacity(0.1))
            row("Network path", d.pathStatus)
            row("Interfaces", d.interfaceTypes)
            Divider().background(Color.white.opacity(0.1))
            row("Meta found", d.metaFound ? "yes" : "no")
            row("Pico local IP", d.localIp)
            Divider().background(Color.white.opacity(0.1))
            row("Probe attempted", d.probeAttempted ? "yes" : "no")
            if d.probeAttempted {
                row("Probe URL", d.probeURL)
                if let ms = d.probeDurationMs { row("Duration", "\(ms) ms") }
                row("Outcome", d.probeOutcome)
            }
            Divider().background(Color.white.opacity(0.1))
            row("Stopped at", d.stoppedAt)
            row("Result", d.finalMode)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding().background(Color(hex: "0F2038")).cornerRadius(12)
    }

    private var historyCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("HISTORY (\(connectionManager.history.count))").font(.caption2.weight(.semibold))
                .foregroundColor(.white.opacity(0.4)).tracking(1)

            ForEach(connectionManager.history) { entry in
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text(entry.timestamp.formatted(date: .omitted, time: .standard))
                            .font(.caption2.monospacedDigit()).foregroundColor(.white.opacity(0.4))
                        Text(entry.trigger)
                            .font(.caption2).foregroundColor(.white.opacity(0.4))
                        Spacer()
                        Text(entry.finalMode)
                            .font(.caption2.weight(.semibold))
                            .foregroundColor(entry.finalMode == "Local" ? Color(hex: "66BB6A") : Color(hex: "FFA726"))
                    }
                    Text(entry.stoppedAt)
                        .font(.caption2).foregroundColor(.white.opacity(0.6))
                    if entry.probeAttempted {
                        Text(entry.probeOutcome)
                            .font(.caption2).foregroundColor(.white.opacity(0.5))
                    }
                }
                .padding(.vertical, 6)
                if entry.id != connectionManager.history.last?.id {
                    Divider().background(Color.white.opacity(0.08))
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding().background(Color(hex: "0F2038")).cornerRadius(12)
    }

    private func row(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top) {
            Text(label).font(.caption).foregroundColor(.white.opacity(0.5))
                .frame(width: 110, alignment: .leading)
            Text(value).font(.caption.monospaced()).foregroundColor(.white.opacity(0.9))
                .textSelection(.enabled)
            Spacer()
        }
    }
}
