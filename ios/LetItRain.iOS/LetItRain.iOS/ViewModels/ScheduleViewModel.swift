// ViewModels/ScheduleViewModel.swift
// Owns all schedule editing state and the auto-builder logic.
// Kept separate from DeviceViewModel so ScheduleView stays clean.

import Foundation
import Combine
import SwiftUI

@MainActor
final class ScheduleViewModel: ObservableObject {

    // MARK: - Published editing state

    @Published var zones:    [ZoneConfig]   = []
    @Published var schedule: WeekSchedule   = .empty
    @Published var selectedDay: Weekday     = .monday

    @Published var hasUnsavedChanges = false
    @Published var isSaving          = false
    @Published var saveError:         String? = nil
    @Published var saveSuccess               = false

    // Auto-builder
    @Published var showAutoBuilder           = false
    @Published var autoBuilderSourceSlot:    ScheduleSlot? = nil
    @Published var autoBuilderSourceDay:     Weekday?      = nil
    @Published var autoBuilderPreview:       [ScheduleSlot] = []
    @Published var autoBuilderApplyAllDays   = false

    // Zone editor sheet
    @Published var showZoneEditor            = false

    // MARK: - Save callback (injected by parent)

    var onSave: ((DeviceConfig) async throws -> Void)?

    // Injected full config reference so we can save non-schedule fields too
    var fullConfig: DeviceConfig = .defaultConfig

    // MARK: - Load

    func load(from config: DeviceConfig) {
        zones            = config.zones
        schedule         = config.schedule
        fullConfig       = config
        hasUnsavedChanges = false
    }

    // MARK: - Day schedule accessors

    var currentDaySchedule: DaySchedule {
        get { schedule[selectedDay] }
        set { schedule[selectedDay] = newValue; hasUnsavedChanges = true }
    }

    func toggleDayEnabled() {
        var d = currentDaySchedule
        d.enabled = !d.enabled
        currentDaySchedule = d
    }

    // MARK: - Slot CRUD

    func addSlot(_ slot: ScheduleSlot) {
        var d = currentDaySchedule
        d.slots.append(slot)
        d.slots = d.slots.sorted { slotMinutes($0) < slotMinutes($1) }
        d.enabled = true
        currentDaySchedule = d
        checkAutoBuilder(newSlot: slot, day: selectedDay)
    }

    func updateSlot(_ slot: ScheduleSlot, at index: Int) {
        var d = currentDaySchedule
        guard index < d.slots.count else { return }
        d.slots[index] = slot
        d.slots = d.slots.sorted { slotMinutes($0) < slotMinutes($1) }
        currentDaySchedule = d
    }

    func deleteSlot(at offsets: IndexSet) {
        var d = currentDaySchedule
        d.slots.remove(atOffsets: offsets)
        currentDaySchedule = d
    }

    func moveSlots(from source: IndexSet, to destination: Int) {
        var d = currentDaySchedule
        d.slots.move(fromOffsets: source, toOffset: destination)
        currentDaySchedule = d
    }

    private func slotMinutes(_ s: ScheduleSlot) -> Int {
        s.startHour * 60 + s.startMinute
    }

    // MARK: - Auto-builder

    /// Called whenever a slot is added for zone 1 (or the first zone).
    /// If there are multiple enabled zones, offer to chain the remaining zones.
    private func checkAutoBuilder(newSlot: ScheduleSlot, day: Weekday) {
        let enabledZones = zones.filter(\.enabled)
        guard enabledZones.count > 1 else { return }

        // Only trigger when a slot for the first zone is added
        guard newSlot.zone == enabledZones.first?.id else { return }

        // Build preview: chain remaining zones sequentially
        var preview: [ScheduleSlot] = []
        var cursor = slotMinutes(newSlot) + newSlot.durationMinutes

        for zone in enabledZones.dropFirst() {
            let h = cursor / 60
            let m = cursor % 60
            guard h < 24 else { break }   // don't overflow into next day
            let slot = ScheduleSlot(
                zone:            zone.id,
                startHour:       h,
                startMinute:     m,
                durationMinutes: newSlot.durationMinutes   // same duration as seed slot
            )
            preview.append(slot)
            cursor += newSlot.durationMinutes
        }

        guard !preview.isEmpty else { return }

        autoBuilderSourceSlot = newSlot
        autoBuilderSourceDay  = day
        autoBuilderPreview    = preview
        autoBuilderApplyAllDays = false
        showAutoBuilder       = true
    }

    /// Accept the auto-builder preview — insert slots into schedule.
    func acceptAutoBuilder() {
        guard let sourceDay = autoBuilderSourceDay else { return }

        let daysToApply: [Weekday] = autoBuilderApplyAllDays
            ? Weekday.allCases.filter { schedule[$0].enabled }
            : [sourceDay]

        for day in daysToApply {
            var d = schedule[day]
            // Remove any existing slots for the zones we're about to add
            // (avoid duplicates if user runs auto-builder more than once)
            let zoneIds = Set(autoBuilderPreview.map(\.zone))
            d.slots.removeAll { zoneIds.contains($0.zone) }
            d.slots.append(contentsOf: autoBuilderPreview)
            d.slots = d.slots.sorted { slotMinutes($0) < slotMinutes($1) }
            schedule[day] = d
        }

        hasUnsavedChanges = true
        showAutoBuilder   = false
    }

    func dismissAutoBuilder() {
        showAutoBuilder = false
    }

    // MARK: - Save

    func save() {
        Task {
            isSaving  = true
            saveError = nil
            var cfg   = fullConfig
            cfg.zones    = zones
            cfg.schedule = schedule
            cfg.zoneCount = zones.filter(\.enabled).count
            do {
                try await onSave?(cfg)
                hasUnsavedChanges = false
                saveSuccess = true
                DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                    self.saveSuccess = false
                }
            } catch {
                saveError = error.localizedDescription
            }
            isSaving = false
        }
    }
}
