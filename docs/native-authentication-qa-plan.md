# Native Authentication QA Plan

## 1. Prerequisites
Before beginning manual validation, ensure the following tools, accounts, and hardware are available:
- **Hardware**:
  - **Android (VALIDATED)**: A physical Android device (Samsung SM-S928B or equivalent running Android 7.0+).
  - **iOS (BLOCKED)**: A physical iPhone (running iOS 15.0+).
  - **Development Machine**: A computer configured with Android SDK Platform Tools (specifically `adb`) and macOS/Xcode for iOS.
- **Accounts**:
  - A Google Test Account (for Google Sign-In verification).
  - An existing manual user account (with password) registered with the same email as the Google Test Account.
  - A new, unregistered email address (for Google first-time registration testing).
- **Console / CLI Access**:
  - USB Debugging enabled on the Android device.
  - Device Console or `cfgutil` access on macOS for iOS log extraction.

---

## 2. Environment Setup
Verify that the following configurations are deployed and verified:
- **Backend API**: The target app must point to the official production API URL. Local or LAN/IP leakage in production builds is prohibited.
- **GCP Console Credentials**:
  - Android Client ID registered with the package name `com.yeshmishak.app` and the SHA-1 fingerprints of the debug/release signing keys.
  - iOS Client ID registered with the matching iOS Bundle ID (once unblocked).
  - Web Client ID configured as the `serverClientId` for the native mobile login plugin.

---

## 3. Android Validation Checklist (VALIDATED)
Use the following commands to validate the Android build on a physical device:

### Installation and Boot
1. Build the debug APK:
   ```bash
   $env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'
   .\gradlew.bat assembleDebug
   ```
2. Install the APK:
   ```bash
   adb install -r -t frontend/android/app/build/outputs/apk/debug/app-debug.apk
   ```
3. Run the application:
   ```bash
   adb shell monkey -p com.yeshmishak.app -c android.intent.category.LAUNCHER 1
   ```

### Force-Stop Relaunch
1. With the user logged in, force-stop the app:
   ```bash
   adb shell am force-stop com.yeshmishak.app
   ```
2. Relaunch the app and confirm the session restores without showing the login screen.

### Uninstall and Backup Verification
1. Log in to the application.
2. Trigger an immediate backup:
   ```bash
   adb shell bmgr backupnow com.yeshmishak.app
   ```
   *Expected Result*: Returns `Backup is not allowed` (confirming `android:allowBackup="false"` is active).
3. Uninstall the application:
   ```bash
   adb uninstall com.yeshmishak.app
   ```
4. Reinstall the application, launch it, and confirm the app starts in the logged-out state and all localStorage user metadata is absent.

---

## 4. iOS Validation Checklist (BLOCKED)
*This checklist is explicitly marked as **BLOCKED** due to a lack of physical iOS hardware.*

### Installation and Launch (EXPECTED)
1. Build the iOS archive and deploy the app via Xcode/TestFlight to a physical iPhone.
2. Launch the application and verify that the `auth-checking` screen displays briefly and resolves to the login screen without flashing.

### Force-Stop and Device Reboot (EXPECTED)
1. With a valid session active, swipe the app closed in the iOS app switcher.
2. Relaunch the app and verify the session restores correctly from the iOS Keychain.
3. Reboot the iPhone, launch the app, and verify the session remains active.

---

## 5. Web Fallback Checklist (VALIDATED)
Verify the Web build behavior using standard web browser developer tools:
1. Load the application on a desktop browser.
2. Verify that the GIS (Google Identity Services) iframe button renders correctly.
3. Authenticate with Google and confirm the JWT is written to `localStorage`.
4. Run `window.localStorage.getItem('access_token')` and verify the token exists.
5. Log out and verify that the token is deleted from `localStorage` and `sessionStorage`.

---

## 6. Google Sign-In Checklist

### Native Account Picker
- **Android (VALIDATED)**: Tap "Continue with Google". Verify the Credential Manager bottom-sheet account picker appears. Select the Google test account and confirm authentication completes.
- **iOS (EXPECTED / BLOCKED)**: Tap the native Google button. Verify that the native iOS authentication sheet renders.

### User Cancellation
- **Android (VALIDATED)**: Tap "Continue with Google". Dismiss the bottom-sheet picker (tap outside or press back). Verify the app returns to the login screen silently with no error banners or console crashes.
- **iOS (EXPECTED / BLOCKED)**: Trigger native login, cancel the native sheet, and verify it fails silently.

### Exchange Validation (VALIDATED)
- Scan network payloads. Verify the native ID token is sent to `POST /auth/google { token: "<idToken>" }` and resolves to the internal app JWT.

---

## 7. Account-Linking 409 Checklist (VALIDATED)
Verify that silent account linking and hijacking are prevented:
1. Register a manual user account using the email `user@example.com` and a password.
2. Initiate a native Google Login using a Google account with the same email (`user@example.com`).
3. Verify that the API returns a `409 Conflict` containing the detail code `ACCOUNT_LINKING_REQUIRED`.
4. Verify that the UI displays exactly:
   `כבר קיים חשבון עם האימייל הזה. התחבר עם סיסמה כדי להמשיך.`
5. Inspect storage via developer tools/ADB and verify that **no JWT or session data is written** to memory, local storage, or secure storage. The user must remain logged out.

---

## 8. Session Restoration Checklist

### No-Flicker Rule (VALIDATED)
- Launch the app from a cold start. Verify that the `auth-checking` loading screen displays. The login screen or map page must not flash before validation completes.

### Read Timeout Simulation (VALIDATED)
- Simulate a hung secure storage bridge (exceeding 5 seconds). Verify that the app resolves to the logged-out login screen (fails closed) instead of hanging indefinitely on the loading screen.

### Background Resume Revalidation (VALIDATED)
- Move the app to the background, then resume it. Verify that the client sends a `GET /games/me` request to revalidate the session (only if logged in). Verify that overlapping resume actions trigger only a single, deduplicated network call.

---

## 9. Logout Cleanup Checklist

### Revocation Validation (VALIDATED)
- Trigger logout. Verify that `POST /auth/logout` is sent with the Authorization header pinned.
- Immediately attempt to make an authenticated request using the discarded token and verify that the backend returns `401 Unauthorized`.

### Storage Deletion (VALIDATED)
- Log out of the application. Verify that the following keys are completely purged:
  - In-memory `cachedToken`
  - LocalStorage: `currentUserId`, `currentUserName`, `currentUserEmail`, `currentUsername`
  - Secure SharedPreferences / Keychain: `access_token`
- Confirm that relaunching the application starts on the login page.

---

## 10. Invalid/Revoked Token Fail-Closed Checklist

### 401 Silent Expiration (VALIDATED)
- Seed a valid-looking but expired JWT.
- Launch the app. Confirm the startup validation `GET /games/me` returns `401 Unauthorized`.
- Verify the app silently redirects to the login screen, purges all local storage metadata, and clears the secure storage token.

### Corrupt Token (VALIDATED)
- Inject a random non-JWT string into the secure storage key `access_token`.
- Launch the app. Confirm the storage read fails or is undecryptable, and verify the app fails closed by deleting the corrupt key and showing the login screen.

---

## 11. Storage Inspection Checklist

### Android SharedPreferences (VALIDATED)
1. Gain access to the application data directory:
   ```bash
   adb shell
   run-as com.yeshmishak.app
   ```
2. Navigate to the shared preferences directory:
   ```bash
   cd shared_prefs/
   cat WSSecureStorageSharedPreferences.xml
   ```
3. Verify that:
   - The token key `access_token` exists and is encrypted (no plaintext `eyJ` prefix is visible).
   - No plaintext passwords, emails, or sessions are stored.

### iOS App Container (EXPECTED / BLOCKED)
1. Inspect the app container sandbox via Xcode Devices window or simulator filesystem.
2. Confirm that no plaintext JWT or credentials exist inside the WebView's `WebKit/WebsiteData/LocalStorage/` directories.

---

## 12. Logging / Token Leak Checklist (VALIDATED)
Verify that no sensitive credential materials are leaked to native debug logs:
1. Stream native device logs:
   - **Android**: `adb logcat | grep -E "eyJ|ya29|accessToken|idToken"`
   - **iOS (Blocked)**: Stream logs via Xcode Console and search for token prefixes.
2. Perform a full login, session restore, and logout cycle.
3. Confirm that **zero** JWT-like structures, Google ID tokens, or bearer authorization values are printed to the logs.

---

## 13. Evidence Collection Format
All native mobile pull requests must attach the following validation evidence before being merged:
1. **Device Specifications**: Brand, model, OS version, and SDK level.
2. **Screen Recording**: A video showing the complete user lifecycle (cold install → login → restart restore → logout → relaunch logged out).
3. **Log Sweep Output**: Copy-paste log snippets of the `grep` scan proving no credential leaks occurred during the validation cycle.
4. **Storage Check Proof**: Text dump of the shared preferences or secure storage preference file proving the token is encrypted and legacy/WebView storages are empty.

---

## 14. Pass/Fail Criteria
- **GO (Pass)**:
  - All automated Playwright and pytest specifications pass.
  - The physical device validation checklist passes completely with zero failures.
  - Zero plain-text tokens or credentials are found in native storage or logs.
- **NO-GO (Fail)**:
  - Any automated test fails.
  - Any step on the physical device validation checklist fails.
  - A plain-text JWT or credential is leaked to `logcat` or WebView local storage.
  - The session fails open (restoring authenticated UI after a 401 or deletion failure).

---

## 15. Blocked / Hardware-Blocked Handling
- In accordance with project policy, iOS native credentials configuration and physical iPhone validation checks are **Hardware-Blocked**.
- Under no circumstances may simulator testing or indirect evidence be accepted as a substitute for physical iPhone validation.
- All iOS-specific checklists in this document must remain marked **BLOCKED / EXPECTED** until a physical iPhone is connected and validated.
