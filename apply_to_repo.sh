#!/bin/bash
# apply_to_repo.sh
# Run this from the ROOT of your cloned LetItRain repository.
# It creates the feature branch, copies all new/modified files, and commits.
#
# Usage:
#   git clone https://github.com/APoythress/LetItRain.git
#   cd LetItRain
#   # Copy this script and the implementation/ folder next to it
#   bash apply_to_repo.sh

set -e

IMPL_DIR="$(dirname "$0")/implementation"

echo "=== LetItRain v1.1.0 Implementation Script ==="
echo ""

# Confirm we're in the right place
if [ ! -f "main.py" ]; then
  echo "ERROR: Run this script from the root of your LetItRain repo."
  echo "       (Expected to find main.py in the current directory)"
  exit 1
fi

# Create and switch to feature branch
echo "→ Creating branch: feature/iosImplementation"
git checkout -b feature/iosImplementation

# ── Pico firmware files ───────────────────────────────────────────────────────

echo "→ Copying firmware files..."

cp "$IMPL_DIR/main.py"        ./main.py
cp "$IMPL_DIR/secrets.py"     ./secrets.py
cp "$IMPL_DIR/version.json"   ./version.json
cp "$IMPL_DIR/README.md"      ./README.md

mkdir -p network
cp "$IMPL_DIR/network/wifi.py"   ./network/wifi.py

mkdir -p firebase
cp "$IMPL_DIR/firebase/__init__.py"       ./firebase/__init__.py
cp "$IMPL_DIR/firebase/client.py"         ./firebase/client.py
cp "$IMPL_DIR/firebase/status_writer.py"  ./firebase/status_writer.py
cp "$IMPL_DIR/firebase/override_reader.py" ./firebase/override_reader.py

# web/server.py replaces the old one
cp "$IMPL_DIR/web/server.py"  ./web/server.py

# ── Cloud Functions ───────────────────────────────────────────────────────────

echo "→ Copying Cloud Functions..."
mkdir -p cloud_functions
cp "$IMPL_DIR/cloud_functions/package.json"        ./cloud_functions/package.json
cp "$IMPL_DIR/cloud_functions/index.js"             ./cloud_functions/index.js
cp "$IMPL_DIR/cloud_functions/ifttt_rain_hook.js"   ./cloud_functions/ifttt_rain_hook.js

# ── iOS app ───────────────────────────────────────────────────────────────────

echo "→ Copying iOS app source..."
mkdir -p ios/LetItRain/Managers
mkdir -p ios/LetItRain/ViewModels
mkdir -p ios/LetItRain/Networking
mkdir -p ios/LetItRain/Models
mkdir -p ios/LetItRain/Views

cp "$IMPL_DIR/ios/README.md"                                    ./ios/README.md
cp "$IMPL_DIR/ios/LetItRain/LetItRainApp.swift"                 ./ios/LetItRain/LetItRainApp.swift
cp "$IMPL_DIR/ios/LetItRain/Managers/ConnectionManager.swift"   ./ios/LetItRain/Managers/ConnectionManager.swift
cp "$IMPL_DIR/ios/LetItRain/ViewModels/AuthViewModel.swift"     ./ios/LetItRain/ViewModels/AuthViewModel.swift
cp "$IMPL_DIR/ios/LetItRain/ViewModels/FirebaseRepository.swift" ./ios/LetItRain/ViewModels/FirebaseRepository.swift
cp "$IMPL_DIR/ios/LetItRain/ViewModels/DeviceViewModel.swift"   ./ios/LetItRain/ViewModels/DeviceViewModel.swift
cp "$IMPL_DIR/ios/LetItRain/Networking/LocalAPIClient.swift"    ./ios/LetItRain/Networking/LocalAPIClient.swift
cp "$IMPL_DIR/ios/LetItRain/Models/DeviceStatus.swift"          ./ios/LetItRain/Models/DeviceStatus.swift
cp "$IMPL_DIR/ios/LetItRain/Models/DeviceConfig.swift"          ./ios/LetItRain/Models/DeviceConfig.swift
cp "$IMPL_DIR/ios/LetItRain/Models/DeviceMeta.swift"            ./ios/LetItRain/Models/DeviceMeta.swift
cp "$IMPL_DIR/ios/LetItRain/Views/ContentView.swift"            ./ios/LetItRain/Views/ContentView.swift
cp "$IMPL_DIR/ios/LetItRain/Views/LoginView.swift"              ./ios/LetItRain/Views/LoginView.swift
cp "$IMPL_DIR/ios/LetItRain/Views/HomeView.swift"               ./ios/LetItRain/Views/HomeView.swift
cp "$IMPL_DIR/ios/LetItRain/Views/DashboardView.swift"          ./ios/LetItRain/Views/DashboardView.swift
cp "$IMPL_DIR/ios/LetItRain/Views/ScheduleView.swift"           ./ios/LetItRain/Views/ScheduleView.swift

# ── .gitignore additions ──────────────────────────────────────────────────────

echo "→ Updating .gitignore..."
cat >> .gitignore << 'GITIGNORE'

# LetItRain v1.1.0 additions
secrets.py
cloud_functions/node_modules/
ios/*.xcodeproj/xcuserdata/
ios/*.xcworkspace/xcuserdata/
*.DS_Store
GoogleService-Info.plist
GITIGNORE

# ── Git commit ────────────────────────────────────────────────────────────────

echo "→ Staging all files..."
git add -A

echo "→ Committing..."
git commit -m "feat: v1.1.0 dual-mode Firebase/local iOS implementation

- Replace HTML web UI with JSON HTTP API (web/server.py)
- Add firebase/ package: client, status_writer, override_reader
- Add network/wifi.py extracted from web/server.py
- Rewrite main.py: Firebase heartbeat + local HTTP server thread
- Add skip-today support (local in-memory + Firebase override)
- Add cloud_functions/: push notifications + IFTTT rain hook stub
- Add ios/ SwiftUI app: dual-mode local/remote ConnectionManager,
  AuthViewModel, FirebaseRepository, DeviceViewModel, LocalAPIClient,
  and all views (Login, Home, Dashboard, Schedule)
- Update README.md with full Firebase and Pico setup instructions
- Add secrets.py stub with per-field setup comments
- Bump version to 1.1.0

Core scheduler, state, relay, DS3231, and config_store unchanged.
IFTTT rain hook schema-ready in overrides node (v1.2 enhancement)."

echo ""
echo "→ Pushing to GitHub..."
git push -u origin feature/iosImplementation

echo ""
echo "✅ Done! Branch feature/iosImplementation pushed to GitHub."
echo ""
echo "Next steps:"
echo "  1. Complete Firebase Console setup (see README.md)"
echo "  2. Fill in secrets.py on the Pico"
echo "  3. Set DHCP reservation for Pico MAC in your router"
echo "  4. Follow ios/README.md to set up the Xcode project"
echo "  5. Deploy Cloud Functions: cd cloud_functions && npm install && firebase deploy --only functions"
