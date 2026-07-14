// ViewModels/AuthViewModel.swift
// Manages Firebase Authentication state.
// This is a private app — no sign-up flow, only sign-in.

import Foundation
import FirebaseAuth

@MainActor
final class AuthViewModel: ObservableObject {

    @Published var isSignedIn:    Bool    = false
    @Published var isLoading:     Bool    = false
    @Published var errorMessage:  String? = nil

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
                self?.isSignedIn = user != nil
            }
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
            isSignedIn = false
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
