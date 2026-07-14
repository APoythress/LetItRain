// Views/LoginView.swift
// Sign-in screen. Rain/water visual theme.
// No sign-up flow — this is a private personal app.

import SwiftUI

struct LoginView: View {

    @EnvironmentObject var authVM: AuthViewModel

    @State private var email    = ""
    @State private var password = ""
    @FocusState private var focusedField: Field?

    enum Field { case email, password }

    var body: some View {
        ZStack {
            // Background gradient
            LinearGradient(
                colors: [Color(hex: "0A1628"), Color(hex: "1A3A5C")],
                startPoint: .top,
                endPoint:   .bottom
            )
            .ignoresSafeArea()

            VStack(spacing: 0) {
                Spacer()

                // Logo / title
                VStack(spacing: 16) {
                    Image(systemName: "cloud.rain.fill")
                        .font(.system(size: 64))
                        .foregroundStyle(
                            LinearGradient(
                                colors: [.white, Color(hex: "64B5F6")],
                                startPoint: .top, endPoint: .bottom
                            )
                        )

                    Text("LetItRain")
                        .font(.system(size: 36, weight: .bold, design: .rounded))
                        .foregroundColor(.white)

                    Text("Sprinkler Controller")
                        .font(.subheadline)
                        .foregroundColor(.white.opacity(0.6))
                }
                .padding(.bottom, 48)

                // Form
                VStack(spacing: 16) {
                    // Email
                    HStack {
                        Image(systemName: "envelope")
                            .foregroundColor(.white.opacity(0.5))
                            .frame(width: 20)
                        TextField("Email", text: $email)
                            .keyboardType(.emailAddress)
                            .autocapitalization(.none)
                            .autocorrectionDisabled()
                            .foregroundColor(.white)
                            .focused($focusedField, equals: .email)
                            .submitLabel(.next)
                            .onSubmit { focusedField = .password }
                    }
                    .padding()
                    .background(Color.white.opacity(0.1))
                    .cornerRadius(12)

                    // Password
                    HStack {
                        Image(systemName: "lock")
                            .foregroundColor(.white.opacity(0.5))
                            .frame(width: 20)
                        SecureField("Password", text: $password)
                            .foregroundColor(.white)
                            .focused($focusedField, equals: .password)
                            .submitLabel(.go)
                            .onSubmit { signIn() }
                    }
                    .padding()
                    .background(Color.white.opacity(0.1))
                    .cornerRadius(12)

                    // Error message
                    if let error = authVM.errorMessage {
                        Text(error)
                            .font(.footnote)
                            .foregroundColor(Color(hex: "FF6B6B"))
                            .multilineTextAlignment(.center)
                            .padding(.horizontal)
                    }

                    // Sign In button
                    Button(action: signIn) {
                        ZStack {
                            if authVM.isLoading {
                                ProgressView().tint(.white)
                            } else {
                                Text("Sign In")
                                    .font(.headline)
                                    .foregroundColor(.white)
                            }
                        }
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(
                            LinearGradient(
                                colors: [Color(hex: "1565C0"), Color(hex: "0D47A1")],
                                startPoint: .leading, endPoint: .trailing
                            )
                        )
                        .cornerRadius(12)
                    }
                    .disabled(authVM.isLoading)
                }
                .padding(.horizontal, 32)

                Spacer()
                Spacer()
            }
        }
    }

    private func signIn() {
        focusedField = nil
        authVM.signIn(email: email, password: password)
    }
}

// MARK: - Color hex extension

extension Color {
    init(hex: String) {
        let hex    = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int    = UInt64(0)
        Scanner(string: hex).scanHexInt64(&int)
        let r, g, b, a: UInt64
        switch hex.count {
        case 6:
            (r, g, b, a) = ((int >> 16) & 0xFF, (int >> 8) & 0xFF, int & 0xFF, 255)
        case 8:
            (r, g, b, a) = ((int >> 24) & 0xFF, (int >> 16) & 0xFF, (int >> 8) & 0xFF, int & 0xFF)
        default:
            (r, g, b, a) = (0, 0, 0, 255)
        }
        self.init(
            .sRGB,
            red:     Double(r) / 255,
            green:   Double(g) / 255,
            blue:    Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}

#Preview {
    LoginView().environmentObject(AuthViewModel())
}
