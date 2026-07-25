// Views/ToastView.swift
// Small transient banner used for success/error feedback across Dashboard and Schedule.

import SwiftUI

enum ToastStyle {
    case success
    case error

    var color: Color {
        switch self {
        case .success: return Color(hex: "34C759")
        case .error:   return Color(hex: "FF453A")
        }
    }

    var icon: String {
        switch self {
        case .success: return "checkmark.circle.fill"
        case .error:   return "exclamationmark.triangle.fill"
        }
    }
}

struct ToastView: View {
    let message: String
    let style:   ToastStyle

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: style.icon)
                .foregroundColor(style.color)
            Text(message)
                .font(.subheadline.weight(.medium))
                .foregroundColor(.white)
                .lineLimit(2)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(Color(hex: "10233F"))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(style.color.opacity(0.5), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .shadow(color: .black.opacity(0.3), radius: 8, y: 2)
        .padding(.horizontal)
    }
}
