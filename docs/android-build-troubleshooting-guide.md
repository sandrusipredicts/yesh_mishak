# Android Build Troubleshooting Guide

## Summary

This is a practical, command-driven troubleshooting guide for the Android/Capacitor build pipeline in this repository. It is based on real issues actually observed during ISSUE-197 through ISSUE-203 (package ID alignment, project structure audit, startup flow validation, API communication validation, network security policy, and network security implementation) — not hypothetical problems. It does not fix anything; it tells you how to diagnose a failure and where to draw the line between "keep debugging" and "file a separate issue."

Golden facts used throughout this guide:

| Item | Value |
| --- | --- |
| Package ID / applicationId | `com.yeshmishak.app` |
| App name | `Yesh Mishak` |
| Web build output dir | `dist` |
| Debug APK path | `frontend/android/app/build/outputs/apk/debug/app-debug.apk` |
| Capacitor WebView origin | `https://localhost` (default `androidScheme: "https"`) |
| Android SDK path (this machine) | `$env:LOCALAPPDATA\Android\Sdk` |
| Working JDK for Gradle CLI | Android Studio's bundled JBR (Java 21), e.g. `C:\Program Files\Android\Android Studio\jbr` |
| Known-bad JDK for Gradle CLI | System JDK 26 |

## Golden Path Commands

This is the sequence that is known to work end-to-end on this project, in order. Every troubleshooting section below assumes you start from this sequence and diagnose wherever it breaks.

```powershell
# Repo root
git status
git branch --show-current

# frontend
cd frontend
npm run build
npx cap sync android
npx cap config

# frontend/android
cd android
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
.\gradlew.bat --version
.\gradlew.bat projects
.\gradlew.bat assembleDebug
.\gradlew.bat :app:processDebugMainManifest

# Device
$ADB = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
& $ADB devices
& $ADB install -r ".\app\build\outputs\apk\debug\app-debug.apk"
& $ADB shell monkey -p com.yeshmishak.app -c android.intent.category.LAUNCHER 1
```

## Quick Diagnostic Flow

Run these checks **in this order**. Stop at the first one that fails — that is your starting point, not the symptom you noticed first.

1. **Confirm repo path.** You should be inside the `yesh_mishak` checkout, not a stale copy or a different clone.
2. **Confirm branch.**
   ```powershell
   git branch --show-current
   ```
3. **Confirm clean working tree** before starting any diagnosis, so you don't confuse your own uncommitted changes with the actual failure:
   ```powershell
   git status
   ```
4. **Confirm Node/npm build** succeeds on its own, independent of Android:
   ```powershell
   npm run build
   ```
5. **Confirm Capacitor sync** succeeds:
   ```powershell
   npx cap sync android
   ```
6. **Confirm Java version** used by Gradle is the Android Studio JBR (Java 21), not a system JDK:
   ```powershell
   .\gradlew.bat --version
   ```
   Look for `JVM:` in the output and confirm it points at the JBR path, not a system Java install.
7. **Confirm Android SDK** is discoverable:
   ```powershell
   echo $env:LOCALAPPDATA\Android\Sdk
   Test-Path "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
   ```
8. **Confirm Gradle build**:
   ```powershell
   .\gradlew.bat assembleDebug
   ```
9. **Confirm device/emulator availability**:
   ```powershell
   & $ADB devices -l
   ```

If everything above passes and you still see a failure, the problem is almost certainly downstream of the build (network/API/CORS — see the dedicated section below), not the build itself.

## Standard Validation Commands

These are the exact commands used across ISSUE-198 through ISSUE-203 for structure audits, startup validation, and API validation. Keep them handy as a reference set, not just a one-time checklist.

**Repo root:**
```powershell
git status
git branch --show-current
```

**`frontend`:**
```powershell
npm run build
npx cap sync android
npx cap config
```
`npx cap config` should report:
- `appId: com.yeshmishak.app`
- `appName: Yesh Mishak`
- `webDir: dist`

**`frontend/android`:**
```powershell
.\gradlew.bat --version
.\gradlew.bat projects
.\gradlew.bat assembleDebug
.\gradlew.bat :app:processDebugMainManifest
```

**ADB:**
```powershell
$ADB = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
& $ADB devices
& $ADB install -r ".\app\build\outputs\apk\debug\app-debug.apk"
& $ADB shell monkey -p com.yeshmishak.app -c android.intent.category.LAUNCHER 1
```

## Gradle Troubleshooting

### Java version mismatch

**Known issue on this project:** the system-default JDK (observed: JDK 26) cannot run Gradle's `androidJdkImage` transform. The observed failure looks like this:

```text
Execution failed for task ':capacitor-android:compileDebugJavaWithJavac'.
> Could not resolve all files for configuration ':capacitor-android:androidJdkImage'.
   > Failed to transform core-for-system-modules.jar ...
      > Error while executing process ...\jlink.exe with arguments {--module-path ... --add-modules java.base ...}
```

**Fix (environment-level, not a project defect):** point `JAVA_HOME` at Android Studio's bundled JBR (Java 21) before running Gradle:

```powershell
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
.\gradlew.bat assembleDebug
```

Verify which JVM Gradle is actually using:

```powershell
.\gradlew.bat --version
```

### Gradle daemon cleanup

If a build hangs, behaves inconsistently after a JDK change, or a prior run was killed mid-build:

```powershell
.\gradlew.bat --stop
```

Then re-run your command. Only reach for `--stop` after a JDK/environment change or a suspicious hang — don't run it reflexively on every failure, since it discards the running daemon's warm state and makes the next build slower.

### Clean build

When incremental state is suspect (stale generated resources, a prior interrupted build, or a config change that doesn't seem to take effect):

```powershell
.\gradlew.bat clean assembleDebug
```

### Dependency / version conflict triage

1. Reproduce with `.\gradlew.bat assembleDebug` first — most dependency conflicts only actually block instrumentation/test tasks, not the production debug APK. Confirm exactly which task fails before assuming the whole build is broken.
2. If the conflict is real, get the dependency tree for the failing configuration:
   ```powershell
   .\gradlew.bat :app:dependencies --configuration debugRuntimeClasspath
   ```
3. Classify: does `assembleDebug` (the real production debug path) pass while only a test/instrumentation task fails? If so, this is very likely the known Kotlin stdlib conflict below — don't block feature work on it, track it separately.

### Known non-blocking `flatDir` warning

Gradle emits, on every configure phase:

```text
WARNING: Using flatDir should be avoided because it doesn't support any meta-data formats.
```

This comes from the generated Capacitor/Cordova bridge configuration (`capacitor.settings.gradle` / `app/capacitor.build.gradle`), not from anything hand-written in this project. It is non-blocking and has been observed across every successful `assembleDebug` run so far. Do not attempt to silence it by hand-editing the generated Capacitor Gradle files — those are regenerated by `npx cap sync android` and manual edits will be lost.

### Known instrumentation Kotlin stdlib conflict

**Observed during ISSUE-197 project structure audit:** building the app's instrumentation test APK fails at `:capacitor-cordova-android-plugins:checkDebugAndroidTestDuplicateClasses` due to a version conflict between `kotlin-stdlib:1.8.22` and older `kotlin-stdlib-jdk7`/`kotlin-stdlib-jdk8:1.6.21` artifacts pulled in transitively.

**How to classify it:**
- Does `.\gradlew.bat assembleDebug` (the production debug APK) pass? If yes, this conflict is isolated to the instrumentation/androidTest path and does **not** block feature work, manual validation, or release builds.
- Only escalate this as urgent if a task specifically requires running connected Android instrumentation tests (e.g. wiring up CI instrumentation tests). Otherwise, track it as a known, separately-scoped dependency alignment cleanup — do not fix it opportunistically inside an unrelated issue.

## SDK / ADB Troubleshooting

### Missing SDK platform / missing build tools

Symptom: Gradle fails with an error naming a missing `platforms;android-XX` or `build-tools;XX.X.X` component. Fix via Android Studio, not by hand-editing SDK folders:

1. Open Android Studio → **Settings/Preferences → Languages & Frameworks → Android SDK**.
2. Under **SDK Platforms**, install the platform version matching `compileSdkVersion`/`targetSdkVersion` in `frontend/android/variables.gradle`.
3. Under **SDK Tools**, install/update **Android SDK Build-Tools** and **Android SDK Platform-Tools**.

### Missing platform-tools / `adb` not recognized

If `adb` is not on `PATH` (common on a fresh machine), do not add it to `PATH` as a workaround inside this repo — use the full path directly:

```powershell
$ADB = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
& $ADB devices
```

If that path doesn't exist, install Platform-Tools from Android Studio (**Settings → Android SDK → SDK Tools → Android SDK Platform-Tools**), then re-check:

```powershell
Test-Path "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
```

### Checking the SDK path

```powershell
echo $env:LOCALAPPDATA\Android\Sdk
Get-ChildItem "$env:LOCALAPPDATA\Android\Sdk"
```

You should see `platform-tools`, `platforms`, and `build-tools` directories. If `$env:LOCALAPPDATA\Android\Sdk` doesn't exist at all, the SDK either isn't installed or was installed to a non-default location — check Android Studio's SDK Manager for the actual configured path rather than guessing.

## Capacitor Sync Troubleshooting

### When to run `npm run build` before `npx cap sync android`

**Always.** `npx cap sync android` copies whatever is currently in `frontend/dist` into `android/app/src/main/assets/public`. If you skip `npm run build` after a frontend change, `cap sync` will happily copy the **stale** `dist` output and you will debug a phantom "my change isn't showing up" issue that has nothing to do with Android. The correct order is always:

```powershell
npm run build
npx cap sync android
```

### What `npx cap config` should show

```powershell
npx cap config
```

Expected, unchanged values:
- `appId: com.yeshmishak.app`
- `appName: Yesh Mishak`
- `webDir: dist`

If any of these differ from what's in `frontend/capacitor.config.ts`, something has overridden the config (e.g. an environment variable or a stray `capacitor.config.json`) — investigate before assuming `capacitor.config.ts` is wrong.

### Common issue: stale web assets

If you see old UI, old strings, or an old bug that you already fixed still showing up on-device:
1. Confirm the fix is actually in `frontend/dist` (`npm run build` again).
2. Re-run `npx cap sync android`.
3. Rebuild and reinstall the APK — installing an old APK over a new one without `-r`, or not rebuilding at all, will also produce this symptom.

### Do not manually edit generated web assets

Never hand-edit anything under `frontend/android/app/src/main/assets/public` or the generated `capacitor.config.json`, `capacitor.settings.gradle`, or `app/capacitor.build.gradle`. These are regenerated by `npx cap sync android` on every sync and any manual edit will silently disappear.

## Manifest / Package Troubleshooting

- **Expected package/applicationId:** `com.yeshmishak.app`, confirmed and aligned across Capacitor `appId`, Gradle `namespace`/`applicationId`, native source path, and Android string resources as of ISSUE-197.
- **Do not add an obsolete `package` attribute to `AndroidManifest.xml`.** Modern Android Gradle Plugin owns the package name via Gradle's `namespace`/`applicationId`, not a manifest `package` attribute. If you see a `package` attribute reappear in the manifest, it's likely from a bad merge or a hand-edit — remove it rather than "fixing" the Gradle files to match it.
- **`MainActivity` package/path alignment:** `frontend/android/app/src/main/java/com/yeshmishak/app/MainActivity.java` must live under a directory path matching its package declaration (`package com.yeshmishak.app;`). If you ever see a build error about a class not being found that "should" be there, check this alignment first.
- **Network Security Config reference:** as of ISSUE-203, `AndroidManifest.xml`'s `<application>` element includes `android:networkSecurityConfig="@xml/network_security_config"`, pointing at `frontend/android/app/src/main/res/xml/network_security_config.xml`. If this attribute or file goes missing, Network Security Config policy silently reverts to Android's per-`targetSdkVersion` default — confirm both still exist after any manifest-touching change.
- **Do not change the package ID casually.** It touches Capacitor `appId`, Gradle `namespace`/`applicationId`, the native Java package directory structure, string resources, and any registered OAuth/Firebase client IDs tied to that package name. Treat any package ID change as its own dedicated, reviewed issue — never a side effect of an unrelated fix.

## Emulator and Device Troubleshooting

### `adb devices` returns empty

```powershell
& $ADB devices -l
```
If no device is listed:
- Confirm USB debugging is enabled on the device (**Settings → Developer options → USB debugging**).
- Confirm the USB cable is a data cable, not charge-only (common with Samsung bundled cables — swap cables before deeper debugging).
- Try a different USB port/mode; some Samsung devices default to "Charging" USB mode and need to be switched to "File transfer" or "PTP" for `adb` to see them reliably.
- Re-run `adb devices` after replugging; the daemon sometimes needs a moment to detect the device.

### Device shows as `unauthorized`

```text
List of devices attached
RFCXA0GMVJA    unauthorized
```
The device is connected but hasn't approved this machine's RSA debugging key yet. Look at the device screen for an "Allow USB debugging?" prompt and accept it (optionally check "Always allow from this computer"). If no prompt appears, unplug/replug the cable, or revoke USB debugging authorizations in Developer Options and reconnect.

### Creating an AVD (emulator alternative)

If no physical device is available, use Android Studio's **Device Manager** to create a Virtual Device matching `compileSdkVersion`/`targetSdkVersion` in `frontend/android/variables.gradle`. Prefer a physical device for network/API validation when possible — the emulator's networking (especially `10.0.2.2` for host loopback) behaves differently from a real device on the same Wi-Fi network, and this project's Android API validation work (ISSUE-200/201) specifically needs real device network behavior.

### Installing the APK

```powershell
& $ADB install -r ".\app\build\outputs\apk\debug\app-debug.apk"
```
`-r` reinstalls over an existing install, preserving app data. Expect `Success` in the output.

### Launching with monkey

```powershell
& $ADB shell am force-stop com.yeshmishak.app
& $ADB shell monkey -p com.yeshmishak.app -c android.intent.category.LAUNCHER 1
```
Force-stopping first ensures you're observing a genuine cold start, not a resumed background process.

### Device locked during validation

If a screenshot or UI dump shows only a lock screen or clock, the device went to sleep/locked mid-session (observed during ISSUE-201). Wake and unlock before continuing:

```powershell
& $ADB shell input keyevent KEYCODE_WAKEUP
& $ADB shell input swipe 500 2000 500 800
```
Then re-screenshot to confirm you're actually looking at the app, not the lock screen, before drawing any conclusions from what you see.

## APK Install / Launch Troubleshooting

- **APK path:** `frontend/android/app/build/outputs/apk/debug/app-debug.apk`. This is regenerated by `.\gradlew.bat assembleDebug` and is never checked into git.
- **Install success criteria:** `adb install -r` prints `Success`; `adb shell pidof com.yeshmishak.app` returns a PID after launch; `adb shell dumpsys activity activities` shows `com.yeshmishak.app/.MainActivity` as the resumed activity.
- **Handling a version downgrade:** if you try to install an APK with a lower `versionCode` than what's installed, `adb install -r` fails with `INSTALL_FAILED_VERSION_DOWNGRADE`. Uninstall first, then install:
  ```powershell
  & $ADB uninstall com.yeshmishak.app
  & $ADB install -r ".\app\build\outputs\apk\debug\app-debug.apk"
  ```
- **Uninstall/reinstall cleanly** (also useful when app state/localStorage is suspected to be stale or corrupted):
  ```powershell
  & $ADB uninstall com.yeshmishak.app
  & $ADB install -r ".\app\build\outputs\apk\debug\app-debug.apk"
  ```
- **Never commit APK artifacts.** `app-debug.apk` and everything else under `app/build/` is a build output, not source. Do not `git add` it, even temporarily, and confirm `git status`/`git diff --name-only` don't show it before any commit in an Android-touching issue.

## Logcat Troubleshooting

### Basic capture flow

```powershell
& $ADB logcat -c
& $ADB shell am force-stop com.yeshmishak.app
& $ADB shell monkey -p com.yeshmishak.app -c android.intent.category.LAUNCHER 1
Start-Sleep -Seconds 10
& $ADB logcat -d -v time > logcat-capture.txt
```

Clearing first (`logcat -c`) is essential — otherwise you're reading through every log line since the device booted, not just the ones from this launch.

### Capturing fatal exceptions

```powershell
& $ADB logcat -d -v time | Select-String -Pattern "AndroidRuntime|FATAL EXCEPTION"
```
Any hit here means a real Android-level crash, not a JS/network issue — investigate the stack trace directly.

### Useful search patterns

```powershell
& $ADB logcat -d -v time | Select-String -Pattern "AndroidRuntime|FATAL EXCEPTION|Capacitor|chromium|Console|CORS|Access-Control|Mixed Content|Firebase|ERR_|HTTP"
```

| Pattern | What it tells you |
| --- | --- |
| `AndroidRuntime`, `FATAL EXCEPTION` | Native Android crash. |
| `Capacitor` | Capacitor bridge activity — asset loading, plugin registration, WebView origin. |
| `chromium` | WebView engine internals — mostly noise, but also where WebView-level warnings surface. |
| `Console` (specifically `Capacitor/Console`) | JavaScript `console.*` output and browser-level errors (including Mixed Content), forwarded from the WebView. This is the most useful tag for diagnosing real API-call failures — see ISSUE-201. |
| `CORS`, `Access-Control` | Backend CORS rejection details, if surfaced to console. |
| `Mixed Content` | HTTPS page blocking an HTTP request — a browser security decision, not a backend or build error (see next section). |
| `Firebase` | Firebase SDK init messages, including missing-config failures. |

### Build errors vs. runtime errors

These are different failure classes and need different fixes — don't conflate them:
- **Build errors** happen during `npm run build`, `npx cap sync android`, or `.\gradlew.bat assembleDebug`, and stop you from producing an APK at all. Fix these using the Gradle/SDK/Capacitor sections above.
- **Runtime errors** happen after a successful install and launch, captured via logcat or on-screen behavior. A successful build proves nothing about runtime correctness — an app can build and install perfectly and still crash, hang, or silently fail API calls. Always check logcat and actual on-device behavior separately from build success, as required in the API communication validation work (ISSUE-201).

## Firebase / Push Troubleshooting

- **Missing `google-services.json`:** observed directly in logcat during ISSUE-201:
  ```text
  W/FirebaseApp: Default FirebaseApp failed to initialize because no default options were found.
  This usually means that com.google.gms:google-services was not applied to your gradle project.
  ```
  Confirmed by searching for the file: none exists anywhere under `frontend/android`.
- **Push notification limitations:** without `google-services.json`, Firebase cannot initialize, so FCM token acquisition and native push token registration cannot function. This is a configuration gap, not a code defect — do not attempt to "fix" it by writing fallback/mock Firebase initialization code.
- **Do not treat a Firebase init failure as a Gradle build failure unless the build actually fails.** `.\gradlew.bat assembleDebug` succeeds with `google-services.json` absent; the failure is a runtime warning, not a build blocker. Check which one you actually have before escalating.
- **Track environment-specific Firebase config separately.** Provisioning `google-services.json` requires access to the project's Firebase console and involves a real secret-bearing config file — this must go through the project's approved secure environment/config process, not be added ad hoc inside an unrelated issue or committed carelessly.

## Network Issues That Are Not Build Issues

These symptoms feel like build problems (they show up while you're doing Android work, sometimes after a fresh install) but are not caused by Gradle, the SDK, or Capacitor at all:

- **CORS is not a build error.** A `400 Disallowed CORS origin` response (confirmed via `curl` OPTIONS preflight in ISSUE-201) is the backend rejecting the request's `Origin` header. No Gradle/Capacitor change can fix this — it requires a backend `CORS_ORIGINS` configuration change (explicitly out of scope for Android-side issues).
- **Mixed Content is not a Gradle error.** The Chromium WebView engine blocking an HTTPS-page's request to an HTTP endpoint (`E/Capacitor/Console: ... Mixed Content: The page at 'https://localhost/' was loaded over HTTPS, but requested an insecure XMLHttpRequest endpoint 'http://...'`) is a browser security decision enforced entirely inside the WebView at runtime. It will not show up as a build failure, and no Gradle/SDK fix resolves it.
- **An HTTP LAN backend is not a valid target for HTTPS WebView API communication.** Capacitor's default `androidScheme` is `https`, so the app always loads at `https://localhost`. Pointing `VITE_API_URL`/`VITE_API_BASE_URL` at a plain `http://` LAN address (as used for early validation in ISSUE-200/201) will always trigger Mixed Content blocking for real in-app requests, regardless of CORS configuration.
- **Network Security Config does not fix backend CORS**, and does not fix Mixed Content either. As implemented in ISSUE-203, `network_security_config.xml` governs whether the Android OS permits cleartext *socket* connections and which CAs are trusted — it has no effect on the backend's CORS allowlist or on Chromium's Mixed Content policy for a WebView page.
- **Bottom line:** real Android API communication needs both an HTTPS backend target and an explicit backend CORS allowance for `https://localhost` (see `docs/android-network-security-requirements.md` and `docs/android-api-communication-validation.md`). If you're debugging a "the app can't talk to the API" issue, check these two things before touching any Android build file.

## Known Project-Specific Issues

| # | Issue | Where observed | Status |
| --- | --- | --- | --- |
| 1 | System JDK 26 cannot run Gradle's `androidJdkImage` transform; must use Android Studio's Java 21 JBR | ISSUE-201, ISSUE-203 | Environment workaround known; set `JAVA_HOME` per session. |
| 2 | Kotlin stdlib version conflict (`kotlin-stdlib:1.8.22` vs `kotlin-stdlib-jdk7`/`jdk8:1.6.21`) breaks the instrumentation/androidTest APK path only | ISSUE-197 | Non-blocking for `assembleDebug`; tracked separately, not yet fixed. |
| 3 | Non-blocking `flatDir` repository warning from generated Capacitor/Cordova Gradle config | ISSUE-198, every observed build | Cosmetic; do not attempt to silence by hand-editing generated files. |
| 4 | `adb` not on `PATH`; must use the full SDK platform-tools path | Every Android validation issue | Use `$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe` directly. |
| 5 | Missing `google-services.json` blocks Firebase init and native push token registration | ISSUE-201 | Known limitation; requires secure provisioning, out of scope for build/debug work. |
| 6 | Android WebView origin is `https://localhost` (Capacitor default `androidScheme: "https"`) | ISSUE-200, ISSUE-201, ISSUE-202 | Expected/by design; drives both the CORS and Mixed Content requirements below. |
| 7 | An HTTP API target (`http://192.168.1.10:8000`) caused a real Mixed Content block during in-app login | ISSUE-201 | Root-caused; fix is to point Android at an HTTPS backend (tracked as follow-up, not yet implemented). |
| 8 | Backend CORS allowlist is missing `https://localhost`, causing `400 Disallowed CORS origin` on every tested endpoint (`/auth/login`, `/auth/google`, `/fields/`, `/games/active`, `/notifications`, `/notifications/push-token`) | ISSUE-200, ISSUE-201 | Root-caused; fix is a backend `CORS_ORIGINS` change (tracked as follow-up, not yet implemented). |

## Decision Tree

Use this to figure out which section of this guide (or which separate issue) actually applies:

```
Does `npm run build` fail?
├─ YES → Frontend/Vite/JS problem. Not an Android issue. Fix in frontend, re-run.
└─ NO
   │
   Does `npx cap sync android` fail?
   ├─ YES → Capacitor Sync Troubleshooting section.
   └─ NO
      │
      Does `.\gradlew.bat assembleDebug` fail?
      ├─ YES → Gradle Troubleshooting section (check JAVA_HOME first).
      └─ NO (APK builds)
         │
         Does `adb install -r` fail?
         ├─ YES → APK Install / Launch Troubleshooting (version downgrade, storage, corrupt APK).
         └─ NO (installs)
            │
            Does the app crash on launch (AndroidRuntime / FATAL EXCEPTION in logcat)?
            ├─ YES → Logcat Troubleshooting → this is a real runtime bug. Escalate per rules below.
            └─ NO (app opens, stays alive)
               │
               Does a real in-app API call (login, fields, games, notifications) fail?
               ├─ YES → Network Issues That Are Not Build Issues section.
               │        Check: CORS preflight, Mixed Content, API base URL scheme.
               └─ NO → Everything is working; if you still see a problem, re-check your assumptions
                        (stale build? wrong device? wrong branch?) before assuming new territory.

Is the device not detected at all (`adb devices` empty or `unauthorized`)?
└─ Emulator and Device Troubleshooting section — this can happen at any point above and blocks
   every device-dependent step until resolved.

Does push/Firebase fail specifically (token registration, FCM init warning)?
└─ Firebase / Push Troubleshooting section — check `google-services.json` presence first.
```

## Escalation Rules

Stop debugging inline and open a separate, dedicated issue when you hit any of the following. Don't fold the fix into whatever issue you were originally working on — these categories have their own review/ownership needs:

- **Gradle dependency conflict** that actually blocks `assembleDebug` (not just instrumentation/test tasks) — needs a deliberate dependency alignment change, reviewed on its own.
- **SDK/JDK environment issue** that isn't resolved by pointing `JAVA_HOME` at the Android Studio JBR — may indicate a broken SDK install or missing components that need Android Studio-level repair, not a code change.
- **Android runtime crash** (`AndroidRuntime`/`FATAL EXCEPTION` in logcat) — this is a real defect in app or native plugin code and needs its own root-cause investigation, not a quick patch mid-validation.
- **Backend CORS/API issue** — as established in ISSUE-200/201/202, this is backend configuration work with its own security review (CORS allowlist changes, HTTPS target changes), never a side fix inside an Android build/validation issue.
- **Firebase config issue** — provisioning `google-services.json` involves real secrets and project-level Firebase console access; route through the approved secure environment process, don't hack around it locally.
- **CI-only failure** (passes locally, fails only in CI) — almost always an environment difference (JDK version, missing SDK components, different `PATH`); treat as its own environment-parity investigation rather than guessing at code changes.

## Final Checklist

Before closing out any Android build/troubleshooting session, confirm:

- [ ] `git status` is clean or only contains the files you intentionally changed.
- [ ] No file under `app/build/`, no `.apk`, and no other build artifact is staged or committed.
- [ ] If you touched the manifest or Network Security Config, `android:networkSecurityConfig="@xml/network_security_config"` is still present and `android:usesCleartextTraffic` was not added.
- [ ] The package ID is still `com.yeshmishak.app` everywhere (Capacitor `appId`, Gradle `namespace`/`applicationId`, native Java package path).
- [ ] You know whether your failure was a **build** failure or a **runtime**/**network** failure, and you fixed (or escalated) the right one.
- [ ] Any unresolved item that matches an Escalation Rule above has its own issue filed, rather than being silently left half-fixed in this session.
