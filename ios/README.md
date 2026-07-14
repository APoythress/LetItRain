# LetItRain iOS App — Xcode Setup

## Prerequisites
- Xcode 15+
- Apple Developer account (paid)
- Firebase project configured (see repo root README)

## Setup Steps

### 1. Create the Xcode Project
1. Open Xcode → File → New → Project
2. Choose **App** (iOS)
3. Settings:
   - Product Name: `LetItRain`
   - Bundle Identifier: `com.yourname.letitrain` ← must match Firebase exactly
   - Interface: SwiftUI
   - Language: Swift
   - Minimum Deployment: iOS 17.0
4. Save the project into this `ios/` folder

### 2. Add Source Files
Drag all `.swift` files from the subdirectories into your Xcode project:
- `LetItRainApp.swift`
- `Managers/ConnectionManager.swift`
- `ViewModels/AuthViewModel.swift`
- `ViewModels/FirebaseRepository.swift`
- `ViewModels/DeviceViewModel.swift`
- `Networking/LocalAPIClient.swift`
- `Models/DeviceStatus.swift`
- `Models/DeviceConfig.swift`
- `Models/DeviceMeta.swift`
- `Views/ContentView.swift`
- `Views/LoginView.swift`
- `Views/HomeView.swift`
- `Views/DashboardView.swift`
- `Views/ScheduleView.swift`

Make sure "Add to target: LetItRain" is checked for all files.

### 3. Add GoogleService-Info.plist
1. Download from Firebase Console → Project Settings → Your apps → iOS app → GoogleService-Info.plist
2. Drag into Xcode project root
3. Check "Add to target: LetItRain" ← critical, easy to miss

### 4. Add Firebase SDK via Swift Package Manager
1. Xcode → File → Add Package Dependencies
2. URL: `https://github.com/firebase/firebase-ios-sdk`
3. Add these products:
   - `FirebaseAuth`
   - `FirebaseDatabase`
   - `FirebaseMessaging`
4. Target: LetItRain

### 5. Add Capabilities
In Xcode → Target → Signing & Capabilities → + Capability:
- **Push Notifications**
- **Background Modes** → check "Remote notifications"

### 6. Upload APNs Key to Firebase
1. Apple Developer Portal → Certificates, IDs & Profiles → Keys → Create new key
2. Check "Apple Push Notifications service (APNs)"
3. Download the .p8 file (you only get one chance)
4. Firebase Console → Project Settings → Cloud Messaging → Apple app configuration
5. Upload the .p8 file, enter the Key ID and Team ID

### 7. Set Signing Team
Xcode → Target → Signing & Capabilities → Team → select your Apple Developer account

### 8. Build & Run
- Select a simulator or your physical iPhone
- Build with Cmd+B to check for errors
- Run with Cmd+R

## First Run
1. Sign in with the email/password you created in Firebase Authentication
2. The app will be in Remote mode until you're on the same Wi-Fi as the Pico
3. In Remote mode: status is read-only, skip-today is available
4. In Local mode: full control — start, stop, schedule configuration

## App Store Submission Checklist
- [ ] App icon added to Assets.xcassets (1024×1024 PNG, no alpha)
- [ ] Screenshots captured for iPhone 6.9" (iPhone 16 Pro Max simulator)
- [ ] Privacy Policy hosted at a public URL (GitHub Pages works)
- [ ] App Store Connect record created with matching bundle ID
- [ ] Archive built via Xcode → Product → Archive
- [ ] Uploaded via Xcode Organizer → Distribute App
