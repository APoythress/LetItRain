// ViewModels/AuthViewModel.swift
// Manages Firebase Authentication state.
// This is a private app — no sign-up flow, only sign-in.

import Foundation
import Combine
import FirebaseAuth
import FirebaseDatabase

@MainActor
final class AuthViewModel: ObservableObject {

    @Published var isSignedIn:        Bool    = false
    @Published var isLoading:         Bool    = false
    @Published var errorMessage:      String? = nil
    @Published var deviceID:          String? = nil
    @Published var isResolvingDevice: Bool    = false

    private var authListener: AuthStateDidChangeListenerHandle?

    init() {
        checkAuthState()
    }

    deinit {
        if let listener = authListener {
            Auth.auth().removeStateDidChangeListener(listener)
        }
    }

    // MARK: - Auth state listener

    func checkAuthState() {
        authListener = Auth.auth().addStateDidChangeListener { [weak self] _, user in
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.isSignedIn = user != nil
                if let user {
                    await self.resolveDeviceID(for: user.uid)
                } else {
                    self.deviceID = nil
                    self.isResolvingDevice = false
                }
            }
        }
    }

    // MARK: - Device resolution

    /// Looks up users/{uid}/device_id -- which physical device this signed-in
    /// person's account is allowed to control. Admin-assigned only (the
    /// security rules make this field read-only from the app); see README's
    /// "Onboarding a new device" section for how it gets set.
    private func resolveDeviceID(for uid: String) async {
        isResolvingDevice = true
        defer { isResolvingDevice = false }
        do {
            let snap = try await Database.database().reference()
                .child("users/\(uid)/device_id")
                .getData()
            deviceID = snap.value as? String
            if deviceID == nil {
                errorMessage = "Your account isn't assigned to a device yet. Contact whoever set up this project."
            }
        } catch {
            errorMessage = "Couldn't determine your device: \(error.localizedDescription)"
        }
    }

    // MARK: - Sign in

    func signIn(email: String, password: String) {
        guard !email.isEmpty, !password.isEmpty else {
            errorMessage = "Please enter your email and password."
            return
        }

        isLoading    = true
        errorMessage = nil

        Task {
            do {
                try await Auth.auth().signIn(withEmail: email, password: password)
                isSignedIn = true
            } catch let error as NSError {
                errorMessage = authErrorMessage(error)
            }
            isLoading = false
        }
    }

    // MARK: - Sign out

    func signOut() {
        do {
            try Auth.auth().signOut()
            isSignedIn        = false
            deviceID          = nil
            isResolvingDevice = false
        } catch {
            errorMessage = "Sign out failed: \(error.localizedDescription)"
        }
    }

    // MARK: - Current user

    var currentUser: User? { Auth.auth().currentUser }
    var currentUID:  String? { currentUser?.uid }

    // MARK: - Error mapping

    private func authErrorMessage(_ error: NSError) -> String {
        switch AuthErrorCode(rawValue: error.code) {
        case .wrongPassword, .invalidCredential:
            return "Incorrect email or password."
        case .invalidEmail:
            return "Please enter a valid email address."
        case .userNotFound:
            return "No account found with that email."
        case .networkError:
            return "Network error. Check your connection and try again."
        default:
            return error.localizedDescription
        }
    }
}
