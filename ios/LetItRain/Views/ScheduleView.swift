// Views/ScheduleView.swift
// Schedule configuration screen. Local mode only.
// Edits config and saves to the Pico via POST /config.

import SwiftUI

struct ScheduleView: View {

    @EnvironmentObject var deviceVM: DeviceViewModel

    // Local edit state — mirrors DeviceConfig.ScheduleConfig
    @State private var enabled:         Bool   = false
    @State private var selectedDays:    Set<Int> = []
    @State private var startHour:       Int    = 6
    @State private var startMinute:     Int    = 0
    @State private var durationMinutes: Int    = 15
    @State private var startTime:       Date   = Calendar.current.date(
        bySettingHour: 6, minute: 0, second: 0, of: Date()
    ) ?? Date()

    @State private var hasChanges = false

    private let dayNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {

                // Schedule enable toggle
                VStack(alignment: .leading, spacing: 0) {
                    Toggle(isOn: $enabled) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Automatic Schedule")
                                .font(.headline)
                                .foregroundColor(.white)
                            Text("Run on selected days at the set time")
                                .font(.caption)
                                .foregroundColor(.white.opacity(0.5))
                        }
                    }
                    .tint(Color(hex: "42A5F5"))
                    .padding()
                    .onChange(of: enabled) { _, _ in hasChanges = true }
                }
                .background(Color(hex: "0F2038"))
                .cornerRadius(16)

                if enabled {
                    // Day picker
                    VStack(alignment: .leading, spacing: 12) {
                        sectionHeader("Run Days")

                        HStack(spacing: 8) {
                            ForEach(0..<7) { dayIndex in
                                let selected = selectedDays.contains(dayIndex)
                                Button {
                                    if selected {
                                        selectedDays.remove(dayIndex)
                                    } else {
                                        selectedDays.insert(dayIndex)
                                    }
                                    hasChanges = true
                                } label: {
                                    Text(dayNames[dayIndex])
                                        .font(.caption.weight(selected ? .semibold : .regular))
                                        .foregroundColor(selected ? .white : .white.opacity(0.4))
                                        .frame(maxWidth: .infinity)
                                        .padding(.vertical, 10)
                                        .background(
                                            selected
                                                ? Color(hex: "1565C0")
                                                : Color(hex: "1E2A3A")
                                        )
                                        .cornerRadius(8)
                                }
                            }
                        }
                    }
                    .padding()
                    .background(Color(hex: "0F2038"))
                    .cornerRadius(16)

                    // Start time picker
                    VStack(alignment: .leading, spacing: 12) {
                        sectionHeader("Start Time")

                        DatePicker(
                            "Start Time",
                            selection: $startTime,
                            displayedComponents: .hourAndMinute
                        )
                        .datePickerStyle(.wheel)
                        .labelsHidden()
                        .colorScheme(.dark)
                        .frame(maxWidth: .infinity)
                        .onChange(of: startTime) { _, newVal in
                            let comps  = Calendar.current.dateComponents([.hour, .minute], from: newVal)
                            startHour   = comps.hour   ?? 6
                            startMinute = comps.minute ?? 0
                            hasChanges = true
                        }
                    }
                    .padding()
                    .background(Color(hex: "0F2038"))
                    .cornerRadius(16)

                    // Duration stepper
                    VStack(alignment: .leading, spacing: 12) {
                        sectionHeader("Run Duration")

                        HStack {
                            Text("\(durationMinutes) minutes")
                                .font(.title3.weight(.medium))
                                .foregroundColor(.white)
                            Spacer()
                            Stepper("", value: $durationMinutes, in: 5...120, step: 5)
                                .labelsHidden()
                                .tint(Color(hex: "42A5F5"))
                                .onChange(of: durationMinutes) { _, _ in hasChanges = true }
                        }
                    }
                    .padding()
                    .background(Color(hex: "0F2038"))
                    .cornerRadius(16)
                }

                // Save button
                Button {
                    saveConfig()
                } label: {
                    HStack {
                        if deviceVM.isLoading {
                            ProgressView().tint(.white)
                        } else {
                            Label("Save Schedule", systemImage: "checkmark.circle.fill")
                                .font(.headline)
                                .foregroundColor(.white)
                        }
                        if hasChanges {
                            Circle()
                                .fill(Color(hex: "FFA726"))
                                .frame(width: 8, height: 8)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(
                        hasChanges
                            ? LinearGradient(colors: [Color(hex: "1565C0"), Color(hex: "0D47A1")],
                                             startPoint: .leading, endPoint: .trailing)
                            : LinearGradient(colors: [Color(hex: "1E2A3A"), Color(hex: "1E2A3A")],
                                             startPoint: .leading, endPoint: .trailing)
                    )
                    .cornerRadius(12)
                }
                .disabled(!hasChanges || deviceVM.isLoading)

                // Success / error messages
                if let msg = deviceVM.successMessage {
                    Text(msg)
                        .font(.footnote)
                        .foregroundColor(Color(hex: "66BB6A"))
                        .frame(maxWidth: .infinity, alignment: .center)
                }
                if let msg = deviceVM.errorMessage {
                    Text(msg)
                        .font(.footnote)
                        .foregroundColor(Color(hex: "FF6B6B"))
                        .frame(maxWidth: .infinity, alignment: .center)
                }
            }
            .padding()
        }
        .background(Color(hex: "0A1628").ignoresSafeArea())
        .navigationBarHidden(true)
        .onAppear(perform: loadFromConfig)
        .onChange(of: deviceVM.config) { _, _ in loadFromConfig() }
    }

    // MARK: - Load from config

    private func loadFromConfig() {
        guard let schedule = deviceVM.config?.schedule else { return }
        enabled         = schedule.enabled
        selectedDays    = Set(schedule.days)
        startHour       = schedule.startHour
        startMinute     = schedule.startMinute
        durationMinutes = schedule.durationMinutes
        startTime       = Calendar.current.date(
            bySettingHour: startHour, minute: startMinute, second: 0, of: Date()
        ) ?? Date()
        hasChanges = false
    }

    // MARK: - Save

    private func saveConfig() {
        guard var config = deviceVM.config else { return }
        config.schedule = DeviceConfig.ScheduleConfig(
            enabled:         enabled,
            days:            Array(selectedDays).sorted(),
            startHour:       startHour,
            startMinute:     startMinute,
            durationMinutes: durationMinutes
        )
        deviceVM.updateConfig(config)
        hasChanges = false
    }

    // MARK: - Helpers

    private func sectionHeader(_ title: String) -> some View {
        Text(title)
            .font(.footnote.weight(.semibold))
            .foregroundColor(.white.opacity(0.5))
            .textCase(.uppercase)
            .tracking(0.5)
    }
}

#Preview {
    ScheduleView()
        .environmentObject(DeviceViewModel(
            connectionManager:  ConnectionManager(),
            firebaseRepository: FirebaseRepository()
        ))
}
