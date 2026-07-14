// Models/DeviceConfig.swift
import Foundation

// MARK: - Zone

struct ZoneConfig: Codable, Identifiable, Equatable {
    var id:      Int
    var name:    String
    var pin:     Int
    var enabled: Bool
}

// MARK: - Schedule Slot

struct ScheduleSlot: Codable, Identifiable, Equatable {
    var id = UUID()                  // client-side only, not sent to Pico/Firebase
    var zone:              Int
    var startHour:         Int
    var startMinute:       Int
    var durationMinutes:   Int

    // Computed start time as a formatted string e.g. "5:00 AM"
    var startTimeString: String {
        let h12  = startHour % 12 == 0 ? 12 : startHour % 12
        let ampm = startHour < 12 ? "AM" : "PM"
        return String(format: "%d:%02d %@", h12, startMinute, ampm)
    }

    // For encoding to Pico/Firebase (snake_case, no id field)
    enum CodingKeys: String, CodingKey {
        case zone
        case startHour         = "start_hour"
        case startMinute       = "start_minute"
        case durationMinutes   = "duration_minutes"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        zone            = try c.decode(Int.self, forKey: .zone)
        startHour       = try c.decode(Int.self, forKey: .startHour)
        startMinute     = try c.decode(Int.self, forKey: .startMinute)
        durationMinutes = try c.decode(Int.self, forKey: .durationMinutes)
    }

    init(zone: Int, startHour: Int, startMinute: Int, durationMinutes: Int) {
        self.zone            = zone
        self.startHour       = startHour
        self.startMinute     = startMinute
        self.durationMinutes = durationMinutes
    }
}

// MARK: - Day Schedule

struct DaySchedule: Codable, Equatable {
    var enabled: Bool
    var slots:   [ScheduleSlot]

    init(enabled: Bool = false, slots: [ScheduleSlot] = []) {
        self.enabled = enabled
        self.slots   = slots
    }
}

// MARK: - Full Schedule

struct WeekSchedule: Codable, Equatable {
    var monday:    DaySchedule
    var tuesday:   DaySchedule
    var wednesday: DaySchedule
    var thursday:  DaySchedule
    var friday:    DaySchedule
    var saturday:  DaySchedule
    var sunday:    DaySchedule

    static var empty: WeekSchedule {
        WeekSchedule(monday: .init(), tuesday: .init(), wednesday: .init(),
                     thursday: .init(), friday: .init(), saturday: .init(), sunday: .init())
    }

    subscript(day: Weekday) -> DaySchedule {
        get {
            switch day {
            case .monday:    return monday
            case .tuesday:   return tuesday
            case .wednesday: return wednesday
            case .thursday:  return thursday
            case .friday:    return friday
            case .saturday:  return saturday
            case .sunday:    return sunday
            }
        }
        set {
            switch day {
            case .monday:    monday    = newValue
            case .tuesday:   tuesday   = newValue
            case .wednesday: wednesday = newValue
            case .thursday:  thursday  = newValue
            case .friday:    friday    = newValue
            case .saturday:  saturday  = newValue
            case .sunday:    sunday    = newValue
            }
        }
    }
}

// MARK: - Weekday enum

enum Weekday: String, CaseIterable, Identifiable {
    case monday, tuesday, wednesday, thursday, friday, saturday, sunday
    var id: String { rawValue }

    var short: String {
        switch self {
        case .monday:    return "Mon"
        case .tuesday:   return "Tue"
        case .wednesday: return "Wed"
        case .thursday:  return "Thu"
        case .friday:    return "Fri"
        case .saturday:  return "Sat"
        case .sunday:    return "Sun"
        }
    }

    var abbreviated: String { String(short.prefix(1)) }
}

// MARK: - DeviceConfig

struct DeviceConfig: Codable, Equatable {
    var deviceName:                   String
    var zoneCount:                    Int
    var zones:                        [ZoneConfig]
    var schedule:                     WeekSchedule
    var manualDefaultDurationMinutes: Int
    var rainSkipThresholdInches:      Double?

    static var defaultConfig: DeviceConfig {
        DeviceConfig(
            deviceName: "LetItRain Controller",
            zoneCount:  1,
            zones: (1...5).map { i in
                ZoneConfig(id: i, name: "Zone \(i)", pin: 16 - i, enabled: i == 1)
            },
            schedule: .empty,
            manualDefaultDurationMinutes: 10,
            rainSkipThresholdInches: nil
        )
    }

    var enabledZones: [ZoneConfig] { zones.filter(\.enabled) }
}
