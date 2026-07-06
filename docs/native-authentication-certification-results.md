# Native Authentication Certification Results

## 1. Metadata
- **Tracking Reference**: ISSUE-249 / GitHub issue #338
- **Goal**: Execute the native authentication certification plan on physical targets and document the results.
- **App Package ID**: `com.yeshmishak.app`
- **Backend API URL**: `http://192.168.1.10:8000` (Development LAN URL configured in `.env`)
- **APK/Build Used**: `frontend/android/app/build/outputs/apk/debug/app-debug.apk`

---

## 2. Tested Hardware & Runtime Environments
- **Android (VALIDATED)**:
  - **Device Model**: Samsung Galaxy S24 Ultra (`SM-S928B`)
  - **OS Version**: Android 16 (API level 36)
- **iOS (BLOCKED)**:
  - **Device Model**: None (Hardware-Blocked; no physical iPhone available for validation).

---

## 3. Exact Commands Run

### Build and Package Compilation
- Build web assets for Android:
  ```powershell
  npm run build:android
  npx cap sync android
  ```
- Compile debug APK:
  ```powershell
  $env:JAVA_HOME='C:\Program Files\Android\Android Studio\jbr'
  cd frontend/android
  .\gradlew.bat assembleDebug
  ```

### Device & Package Audits
- Verify connected devices:
  ```powershell
  & "C:\Users\orel1\AppData\Local\Android\Sdk\platform-tools\adb.exe" devices
  ```
- Verify product model:
  ```powershell
  & "C:\Users\orel1\AppData\Local\Android\Sdk\platform-tools\adb.exe" shell getprop ro.product.model
  ```
- Verify OS release:
  ```powershell
  & "C:\Users\orel1\AppData\Local\Android\Sdk\platform-tools\adb.exe" shell getprop ro.build.version.release
  ```
- Install APK:
  ```powershell
  & "C:\Users\orel1\AppData\Local\Android\Sdk\platform-tools\adb.exe" install -r -t frontend/android/app/build/outputs/apk/debug/app-debug.apk
  ```
- Verify backup policy:
  ```powershell
  & "C:\Users\orel1\AppData\Local\Android\Sdk\platform-tools\adb.exe" shell bmgr backupnow com.yeshmishak.app
  ```

---

## 4. Manual Test Matrix

| Test Case | Platform | Result | Evidence / Logs |
| :--- | :--- | :--- | :--- |
| **Fresh Install & Boot** | Android | **PASS** | Installed successfully; starts on logged-out login page with no flicker. |
| | iOS | **BLOCKED** | Gated by lack of physical iPhone. |
| **Google Sign-In** | Android | **PASS** | Native Credential Manager sheet renders, account selected, auth completes. |
| | iOS | **BLOCKED** | Gated by lack of physical iPhone. |
| **Verify Authenticated UI** | Android | **PASS** | Profile metadata loads; Toolbar displays name; Map markers load. |
| | iOS | **BLOCKED** | Gated by lack of physical iPhone. |
| **Session Relaunch Survival** | Android | **PASS** | Swiping app closed and relaunching retains the validated session. |
| | iOS | **BLOCKED** | Gated by lack of physical iPhone. |
| **Session Force-Stop Survival** | Android | **PASS** | `adb shell am force-stop` doesn't affect key persistence. Session recovers. |
| | iOS | **BLOCKED** | Gated by lack of physical iPhone. |
| **Session Device Restart Survival**| Android | **PASS** | Device reboot survives; token remains secure in Keystore-backed storage. |
| | iOS | **BLOCKED** | Gated by lack of physical iPhone. |
| **Logout Clears Auth State** | Android | **PASS** | Tap logout → clears cached tokens, local metadata, and revokes JWT. |
| | iOS | **BLOCKED** | Gated by lack of physical iPhone. |
| **Post-Logout Relaunch** | Android | **PASS** | App relaunch after logout starts clean on login page. |
| | iOS | **BLOCKED** | Gated by lack of physical iPhone. |
| **Post-Logout Device Restart** | Android | **PASS** | Device reboot after logout stays logged out. |
| | iOS | **BLOCKED** | Gated by lack of physical iPhone. |
| **Local/SessionStorage Leakage** | Android | **PASS** | Inspected WebView local storage keys: no JWT or credentials present. |
| | iOS | **BLOCKED** | Gated by lack of physical iPhone. |
| **Storage Inspection (Encrypted)** | Android | **PASS** | `cat WSSecureStorageSharedPreferences.xml` confirms token is encrypted. |
| | iOS | **BLOCKED** | Gated by lack of physical iPhone. |
| **Logcat Token Leakage Scan** | Android | **PASS** | `adb logcat \| grep -E "eyJ\|ya29"` returned zero results during usage. |
| | iOS | **BLOCKED** | Gated by lack of physical iPhone. |
| **Account-Linking 409 Block** | Android | **PASS** | Email match with manual account displays Hebrew message and fails closed. |
| | iOS | **BLOCKED** | Gated by lack of physical iPhone. |

---

## 5. Storage & Security Verification
- **Auto-Backup Exclusion (VALIDATED)**:
  - Running `adb shell bmgr backupnow com.yeshmishak.app` returned:
    ```text
    Package com.yeshmishak.app with result: Backup is not allowed
    ```
    This confirms `android:allowBackup="false"` and the exclusion files are correctly enforced at runtime.
- **Secure Preferences Isolation (VALIDATED)**:
  - `run-as com.yeshmishak.app` verified that the shared preferences file `WSSecureStorageSharedPreferences.xml` contains the encrypted token ciphertext; no plain `access_token` values exist.

---

## 6. Failures and Blockers
- **iOS Validation**: Completely **BLOCKED** due to missing physical hardware (iPhone). Simulator validation is insufficient per the cross-platform standards document.

---

## 7. Final Certification Verdict
- **Android Target**: **GO**
  All Android native authentication, logout, session restoration, and backup security validation checklists have passed successfully. No defects remain open.
- **iOS Target**: **BLOCKED**
  The iOS target is blocked.
- **Global Release Status**: **Android Validated, iOS Blocked (Hardware-Blocked)**

---

## 8. No-Touch / Governance Confirmation
- Backend, iOS native code, configurations, database migrations, and dependency package files remain completely untouched.
