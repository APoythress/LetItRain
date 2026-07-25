// Views/ScheduleView.swift
// Multi-zone schedule builder with per-day multi-slot management and auto-builder.

import SwiftUI

// MARK: - Root

struct ScheduleView: View {
    @EnvironmentObject var deviceVM: DeviceViewModel

    var body: some View {
        ScheduleRootView(vm: deviceVM.scheduleVM)
            .environmentObject(deviceVM)
    }
}

// MARK: - ScheduleRootView

struct ScheduleRootView: View {

    @ObservedObject var vm: ScheduleViewModel
    @EnvironmentObject var deviceVM: DeviceViewModel

    @State private var showAddSlot   = false
    @State private var editingSlot:   EditingSlotWrapper? = nil

    var body: some View {
        ZStack(alignment: .top) {
            Color(hex: "0A1628").ignoresSafeArea()

            VStack(spacing: 0) {
                zoneHeader
                dayPicker
                dayContent
                if vm.hasUnsavedChanges { saveBar }
            }
        }
        .sheet(isPresented: $showAddSlot) {
            SlotEditorSheet(vm: vm, editingSlot: nil, day: vm.selectedDay) { vm.addSlot($0) }
        }
        .sheet(item: $editingSlot) { wrapper in
            SlotEditorSheet(vm: vm, editingSlot: wrapper.slot, day: vm.selectedDay) {
                vm.updateSlot($0, at: wrapper.index)
            }
        }
        .sheet(isPresented: $vm.showAutoBuilder) { AutoBuilderSheet(vm: vm) }
        .sheet(isPresented: $vm.showZoneEditor)  { ZoneEditorSheet(vm: vm) }
        .overlay(alignment: .top) {
            VStack {
                if vm.saveSuccess {
                    ToastView(message: "Schedule saved!", style: .success).padding(.top, 12)
                        .transition(.move(edge: .top).combined(with: .opacity))
                }
                if let err = vm.saveError {
                    ToastView(message: err, style: .error).padding(.top, 12)
                        .transition(.move(edge: .top).combined(with: .opacity))
                }
            }
            .animation(.easeInOut(duration: 0.3), value: vm.saveSuccess)
            .animation(.easeInOut(duration: 0.3), value: vm.saveError)
        }
    }

    // MARK: Zone header

    private var zoneHeader: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("Schedule")
                    .font(.title2.weight(.bold)).foregroundColor(.white)
                let count = vm.zones.filter(\.enabled).count
                Text("\(count) zone\(count == 1 ? "" : "s") active")
                    .font(.caption).foregroundColor(.white.opacity(0.5))
            }
            Spacer()
            Button { vm.showZoneEditor = true } label: {
                Label("Zones", systemImage: "slider.horizontal.3")
                    .font(.subheadline.weight(.medium))
                    .foregroundColor(Color(hex: "64B5F6"))
                    .padding(.horizontal, 14).padding(.vertical, 8)
                    .background(Color(hex: "1565C0").opacity(0.3))
                    .cornerRadius(20)
            }
        }
        .padding().background(Color(hex: "0F2038"))
    }

    // MARK: Day picker

    private var dayPicker: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(Weekday.allCases) { day in
                    let d     = vm.schedule[day]
                    let isSel = vm.selectedDay == day
                    Button { vm.selectedDay = day } label: {
                        VStack(spacing: 4) {
                            Text(day.short)
                                .font(.caption.weight(isSel ? .bold : .regular))
                                .foregroundColor(isSel ? .white : .white.opacity(0.5))
                            Circle()
                                .fill(d.slots.isEmpty ? Color.clear :
                                      d.enabled ? Color(hex: "42A5F5") : Color(hex: "555"))
                                .frame(width: 5, height: 5)
                        }
                        .padding(.horizontal, 12).padding(.vertical, 8)
                        .background(isSel ? Color(hex: "1565C0") : Color(hex: "1E2A3A"))
                        .cornerRadius(10)
                    }
                }
            }
            .padding(.horizontal).padding(.vertical, 10)
        }
        .background(Color(hex: "0F2038"))
    }

    // MARK: Day content

    private var dayContent: some View {
        ScrollView {
            VStack(spacing: 12) {

                // Enable toggle
                Toggle(isOn: Binding(
                    get: { vm.currentDaySchedule.enabled },
                    set: { _ in vm.toggleDayEnabled() }
                )) {
                    Text("Enable \(vm.selectedDay.short) schedule")
                        .font(.subheadline).foregroundColor(.white)
                }
                .tint(Color(hex: "42A5F5"))
                .padding().background(Color(hex: "0F2038")).cornerRadius(12)

                // Slots
                if vm.currentDaySchedule.slots.isEmpty {
                    emptyState
                } else {
                    VStack(spacing: 0) {
                        ForEach(Array(vm.currentDaySchedule.slots.enumerated()), id: \.element.id) { i, slot in
                            SlotRow(
                                slot:     slot,
                                zones:    vm.zones,
                                onEdit:   { editingSlot = EditingSlotWrapper(slot: slot, index: i) },
                                onDelete: { vm.deleteSlot(at: IndexSet(integer: i)) }
                            )
                            if i < vm.currentDaySchedule.slots.count - 1 {
                                Divider().background(Color.white.opacity(0.08))
                            }
                        }
                    }
                    .background(Color(hex: "0F2038")).cornerRadius(12)
                }

                // Add slot
                Button { showAddSlot = true } label: {
                    Label("Add Time Slot", systemImage: "plus.circle.fill")
                        .font(.subheadline.weight(.medium))
                        .foregroundColor(Color(hex: "64B5F6"))
                        .frame(maxWidth: .infinity).padding()
                        .background(Color(hex: "1565C0").opacity(0.2))
                        .cornerRadius(12)
                        .overlay(RoundedRectangle(cornerRadius: 12)
                            .stroke(Color(hex: "1565C0").opacity(0.4), lineWidth: 1))
                }
            }
            .padding()
        }
    }

    private var emptyState: some View {
        VStack(spacing: 10) {
            Image(systemName: "calendar.badge.plus").font(.system(size: 32))
                .foregroundColor(.white.opacity(0.2))
            Text("No slots for \(vm.selectedDay.short)")
                .font(.subheadline).foregroundColor(.white.opacity(0.4))
            Text("Tap 'Add Time Slot' below to get started")
                .font(.caption).foregroundColor(.white.opacity(0.3))
        }
        .frame(maxWidth: .infinity).padding(32)
        .background(Color(hex: "0F2038")).cornerRadius(12)
    }

    // MARK: Save bar

    private var saveBar: some View {
        HStack(spacing: 12) {
            Button {
                if let cfg = deviceVM.config { vm.load(from: cfg) }
            } label: {
                Text("Discard")
                    .font(.subheadline).foregroundColor(.white.opacity(0.6))
                    .frame(maxWidth: .infinity).padding(.vertical, 14)
                    .background(Color(hex: "1E2A3A")).cornerRadius(12)
            }
            Button { vm.save() } label: {
                HStack {
                    if vm.isSaving { ProgressView().tint(.white).scaleEffect(0.8) }
                    Text(vm.isSaving ? "Saving…" : "Save")
                        .font(.subheadline.weight(.semibold)).foregroundColor(.white)
                }
                .frame(maxWidth: .infinity).padding(.vertical, 14)
                .background(LinearGradient(colors: [Color(hex: "1565C0"), Color(hex: "0D47A1")],
                                           startPoint: .leading, endPoint: .trailing))
                .cornerRadius(12)
            }
            .disabled(vm.isSaving)
        }
        .padding().background(Color(hex: "0F2038"))
    }
}

// MARK: - SlotRow

struct SlotRow: View {
    let slot: ScheduleSlot; let zones: [ZoneConfig]
    let onEdit: () -> Void; let onDelete: () -> Void

    private var zoneName: String {
        zones.first { $0.id == slot.zone }?.name ?? "Zone \(slot.zone)"
    }

    var body: some View {
        HStack(spacing: 14) {
            VStack(alignment: .leading, spacing: 2) {
                Text(slot.startTimeString)
                    .font(.headline.monospacedDigit()).foregroundColor(.white)
                Text("\(slot.durationMinutes) min")
                    .font(.caption).foregroundColor(.white.opacity(0.5))
            }
            Text(zoneName)
                .font(.caption.weight(.medium)).foregroundColor(Color(hex: "64B5F6"))
                .padding(.horizontal, 10).padding(.vertical, 4)
                .background(Color(hex: "1565C0").opacity(0.3)).cornerRadius(8)
            Spacer()
            Button(action: onEdit)   { Image(systemName: "pencil").foregroundColor(.white.opacity(0.5)) }
            Button(action: onDelete) { Image(systemName: "trash").foregroundColor(Color(hex: "FF6B6B").opacity(0.7)) }
        }
        .padding(.horizontal, 16).padding(.vertical, 14)
    }
}

// MARK: - SlotEditorSheet

struct SlotEditorSheet: View {
    @Environment(\.dismiss) var dismiss
    @ObservedObject var vm: ScheduleViewModel
    var editingSlot: ScheduleSlot?
    var day: Weekday
    var onSave: (ScheduleSlot) -> Void

    @State private var selectedZone    = 1
    @State private var startTime: Date = Calendar.current.date(bySettingHour: 6, minute: 0, second: 0, of: Date()) ?? Date()
    @State private var duration        = 15

    var body: some View {
        NavigationView {
            ZStack {
                Color(hex: "0A1628").ignoresSafeArea()
                ScrollView {
                    VStack(spacing: 16) {

                        // Zone picker
                        card(title: "Zone") {
                            ScrollView(.horizontal, showsIndicators: false) {
                                HStack(spacing: 8) {
                                    ForEach(vm.zones.filter(\.enabled)) { zone in
                                        Button { selectedZone = zone.id } label: {
                                            Text(zone.name)
                                                .font(.subheadline.weight(selectedZone == zone.id ? .semibold : .regular))
                                                .foregroundColor(selectedZone == zone.id ? .white : .white.opacity(0.5))
                                                .padding(.horizontal, 16).padding(.vertical, 10)
                                                .background(selectedZone == zone.id ? Color(hex: "1565C0") : Color(hex: "1E2A3A"))
                                                .cornerRadius(10)
                                        }
                                    }
                                }
                            }
                        }

                        // Time
                        card(title: "Start Time") {
                            DatePicker("", selection: $startTime, displayedComponents: .hourAndMinute)
                                .datePickerStyle(.wheel).labelsHidden().colorScheme(.dark).frame(maxWidth: .infinity)
                        }

                        // Duration
                        card(title: "Duration") {
                            HStack {
                                Text("\(duration) minutes").font(.title3.weight(.medium)).foregroundColor(.white)
                                Spacer()
                                Stepper("", value: $duration, in: 1...120, step: 5).labelsHidden().tint(Color(hex: "42A5F5"))
                            }
                        }
                    }
                    .padding()
                }
            }
            .navigationTitle(editingSlot == nil ? "Add Slot — \(day.short)" : "Edit Slot")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }.foregroundColor(.white.opacity(0.6))
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        let c = Calendar.current.dateComponents([.hour, .minute], from: startTime)
                        onSave(ScheduleSlot(zone: selectedZone, startHour: c.hour ?? 6,
                                            startMinute: c.minute ?? 0, durationMinutes: duration))
                        dismiss()
                    }
                    .foregroundColor(Color(hex: "64B5F6")).fontWeight(.semibold)
                }
            }
        }
        .onAppear {
            if let s = editingSlot {
                selectedZone = s.zone; duration = s.durationMinutes
                startTime = Calendar.current.date(bySettingHour: s.startHour, minute: s.startMinute, second: 0, of: Date()) ?? Date()
            } else {
                selectedZone = vm.zones.filter(\.enabled).first?.id ?? 1
            }
        }
    }

    private func card<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).font(.footnote.weight(.semibold)).foregroundColor(.white.opacity(0.5))
                .textCase(.uppercase).tracking(0.5)
            content()
        }
        .padding().background(Color(hex: "0F2038")).cornerRadius(12)
    }
}

// MARK: - AutoBuilderSheet

struct AutoBuilderSheet: View {
    @ObservedObject var vm: ScheduleViewModel

    var body: some View {
        NavigationView {
            ZStack {
                Color(hex: "0A1628").ignoresSafeArea()
                ScrollView {
                    VStack(spacing: 16) {

                        // Header
                        VStack(spacing: 12) {
                            Image(systemName: "wand.and.stars").font(.system(size: 40))
                                .foregroundColor(Color(hex: "FFA726"))
                            Text("Auto-Build Schedule").font(.title3.weight(.bold)).foregroundColor(.white)
                            if let src = vm.autoBuilderSourceSlot {
                                Text("Zone \(src.zone) runs at \(src.startTimeString) for \(src.durationMinutes) min.\nWant to chain the remaining zones back-to-back?")
                                    .font(.subheadline).foregroundColor(.white.opacity(0.6)).multilineTextAlignment(.center)
                            }
                        }
                        .padding().frame(maxWidth: .infinity).background(Color(hex: "0F2038")).cornerRadius(12)

                        // Preview
                        VStack(alignment: .leading, spacing: 0) {
                            Text("ZONES TO ADD").font(.caption2.weight(.semibold))
                                .foregroundColor(.white.opacity(0.4)).tracking(1)
                                .padding(.horizontal).padding(.top, 12).padding(.bottom, 6)
                            ForEach(Array(vm.autoBuilderPreview.enumerated()), id: \.element.id) { i, slot in
                                HStack {
                                    Image(systemName: "drop.fill").foregroundColor(Color(hex: "42A5F5")).frame(width: 20)
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text("Zone \(slot.zone)").font(.subheadline.weight(.medium)).foregroundColor(.white)
                                        Text("\(slot.startTimeString)  ·  \(slot.durationMinutes) min")
                                            .font(.caption).foregroundColor(.white.opacity(0.5))
                                    }
                                    Spacer()
                                }
                                .padding(.horizontal).padding(.vertical, 10)
                                if i < vm.autoBuilderPreview.count - 1 {
                                    Divider().background(Color.white.opacity(0.08)).padding(.leading)
                                }
                            }
                        }
                        .background(Color(hex: "0F2038")).cornerRadius(12)

                        // Apply all days
                        Toggle(isOn: $vm.autoBuilderApplyAllDays) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Apply to all enabled days").font(.subheadline).foregroundColor(.white)
                                Text("Copies this sequence to every day that has a schedule enabled")
                                    .font(.caption).foregroundColor(.white.opacity(0.5))
                            }
                        }
                        .tint(Color(hex: "42A5F5")).padding().background(Color(hex: "0F2038")).cornerRadius(12)

                        // Info
                        HStack(spacing: 8) {
                            Image(systemName: "info.circle").foregroundColor(Color(hex: "64B5F6"))
                            Text("All slots are editable after applying.")
                                .font(.caption).foregroundColor(.white.opacity(0.5))
                        }
                        .padding(.horizontal)
                    }
                    .padding()
                }
            }
            .navigationTitle("Auto-Builder")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Skip") { vm.dismissAutoBuilder() }.foregroundColor(.white.opacity(0.5))
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Apply") { vm.acceptAutoBuilder() }
                        .foregroundColor(Color(hex: "FFA726")).fontWeight(.semibold)
                }
            }
        }
    }
}

// MARK: - ZoneEditorSheet

struct ZoneEditorSheet: View {
    @Environment(\.dismiss) var dismiss
    @ObservedObject var vm: ScheduleViewModel

    var body: some View {
        NavigationView {
            ZStack {
                Color(hex: "0A1628").ignoresSafeArea()
                List {
                    ForEach($vm.zones) { $zone in
                        VStack(alignment: .leading, spacing: 10) {
                            TextField("e.g. Front Lawn", text: Binding(
                                get: { zone.name },
                                set: { zone.name = $0; vm.hasUnsavedChanges = true }
                            )).font(.title2).foregroundColor(.white)

                            Toggle(isOn: Binding(
                                get: { zone.enabled },
                                set: { zone.enabled = $0; vm.hasUnsavedChanges = true }
                            )) {
                                Text("Enabled")
                                    .font(.subheadline).foregroundColor(.white.opacity(0.5))
                            }
                            .tint(Color(hex: "42A5F5"))

                            if zone.enabled {
                                Spacer()

                                HStack {
                                    Text("GPIO Pin").font(.caption).foregroundColor(.white.opacity(0.5))
                                    Spacer()
                                    Stepper("GPIO \(zone.pin)", value: Binding(
                                        get: { zone.pin },
                                        set: { zone.pin = $0; vm.hasUnsavedChanges = true }
                                    ), in: 0...28)
                                    .foregroundColor(.white)
                                }
                            }
                        }
                        .listRowBackground(Color(hex: "0F2038"))
                    }
                }
                .listStyle(.insetGrouped).scrollContentBackground(.hidden)
            }
            .navigationTitle("Configure Zones")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }.foregroundColor(Color(hex: "64B5F6"))
                }
            }
        }
    }
}

// MARK: - Helpers

private struct EditingSlotWrapper: Identifiable {
    let id    = UUID()
    let slot:  ScheduleSlot
    let index: Int
}
