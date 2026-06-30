# Android Development Environment Setup Guide

**ISSUE:** 196
**Date:** 2026-06-30
**Status:** Official setup reference
**Scope:** Documentation only - no Gradle, Capacitor, or native project changes

---

## 1. Purpose

This is the official local setup guide for building and validating the Yesh Mishak Capacitor Android project. Follow these steps to configure Android Studio, SDK, emulator, and JDK so that the Android debug build compiles and runs consistently.

---

## 2. Project Context

| Property | Value |
| :--- | :--- |
| Frontend project path | `frontend/` |
| Android project path | `frontend/android/` |
| Capacitor appId | `com.yeshmishak.app` |
| Capacitor appName | `Yesh Mishak` |
| Capacitor webDir | `dist` |
| `@capacitor/android` | 8.4.1 |
| `@capacitor/core` | 8.4.1 |
| `@capacitor/cli` | 8.4.1 |
| Gradle wrapper | 8.14.3 |
| minSdkVersion | 24 (Android 7.0) |
| compileSdkVersion | 36 |
| targetSdkVersion | 36 |
| Java source compatibility | 21 |

---

## 3. Required Tools

| Tool | Purpose | Required |
| :--- | :--- | :--- |
| Node.js | Run npm, Vite build, Capacitor CLI | Yes |
| npm | Dependency management | Yes |
| Android Studio | IDE, SDK Manager, Emulator, Gradle integration | Yes |
| Android SDK Platform API 24+ | Compile and target Android builds | Yes |
| Android SDK Build-Tools | Build APK/AAB | Yes |
| Android SDK Platform-Tools | ADB, device communication | Yes |
| Android Emulator | Run the app without a physical device | Yes (or physical device) |
| JDK (compatible with Gradle) | Compile Android code | Yes |

---

## 4. Version Guidance

### 4.1 Android Studio

Use Android Studio compatible with Capacitor 8. Minimum recommended version: **Android Studio 2025.2.1** (Narwhal) or newer.

### 4.2 Android SDK

Install SDK Platform **API 24 or newer**. The project compiles against API 36 and targets API 36, with a minimum SDK of 24.

### 4.3 JDK / Gradle Compatibility

The project uses **Gradle 8.14.3** (via the Gradle wrapper in `frontend/android/gradle/wrapper/gradle-wrapper.properties`). The Capacitor-generated build files set `sourceCompatibility JavaVersion.VERSION_21`.

**Recommended Gradle runtime JDK: JDK 21 or JDK 17.**

Prefer the JDK bundled with Android Studio (Embedded JBR) for IDE and Gradle usage. Set Android Studio Gradle JDK and terminal `JAVA_HOME` consistently.

**Do not use Java 26 as the Gradle runtime.** ISSUE-195 validation confirmed that Java 26 (class file major version 70) causes Gradle to fail with `Unsupported class file major version 70`. Java 26 is not the project standard for Gradle execution.

| JDK | Gradle 8.14.3 Compatibility | Recommended |
| :--- | :--- | :--- |
| Embedded JBR (Android Studio) | Compatible | Yes (preferred) |
| JDK 21 | Compatible | Yes |
| JDK 17 | Compatible | Yes |
| JDK 26 | **Not compatible** | No |

---

## 5. Android Studio Setup

### 5.1 Install Android Studio

Download and install Android Studio from the official site. Use version 2025.2.1 (Narwhal) or newer.

### 5.2 Open SDK Manager

In Android Studio:

**Tools -> SDK Manager**

Or from the Welcome screen:

**More Actions -> SDK Manager**

### 5.3 Install SDK Platform

Under the **SDK Platforms** tab, install:

- Android API 36 (or the latest stable API level)
- Ensure API 24 or newer is available

Check **Show Package Details** to see individual components.

### 5.4 Install SDK Tools

Under the **SDK Tools** tab, install:

- Android SDK Build-Tools (latest stable)
- Android SDK Platform-Tools
- Android Emulator
- Android SDK Command-line Tools (latest)

### 5.5 Open the Project

Option A - from terminal:

```
cd frontend
npx cap open android
```

Option B - from Android Studio:

**File -> Open** -> navigate to `frontend/android/` -> Open

Android Studio should recognize the Gradle project, sync dependencies, and show the `app` module.

---

## 6. Gradle JDK Setup

### 6.1 Configure in Android Studio

Navigate to:

**File -> Settings -> Build, Execution, Deployment -> Build Tools -> Gradle -> Gradle JDK**

Select one of:

1. **Embedded JBR** (preferred - bundled with Android Studio)
2. **JDK 21** (if installed separately)
3. **JDK 17** (if installed separately)

**Do not select Java 26** for this project's current Gradle setup.

### 6.2 Verify from Terminal

If running Gradle from the terminal (outside Android Studio), ensure `JAVA_HOME` points to a compatible JDK:

```powershell
java -version
echo $env:JAVA_HOME
```

If `java -version` shows Java 26, set `JAVA_HOME` to a compatible JDK before running Gradle:

```powershell
$env:JAVA_HOME = "C:\Path\To\JDK21"
```

Or configure `JAVA_HOME` permanently in Windows System Environment Variables.

---

## 7. Environment Variables

### 7.1 Verification Commands

```powershell
java -version
echo $env:JAVA_HOME
echo $env:ANDROID_HOME
echo $env:ANDROID_SDK_ROOT
```

### 7.2 Expected Meaning

| Variable | Purpose | Notes |
| :--- | :--- | :--- |
| `JAVA_HOME` | JDK used by Gradle and CLI tools | Must point to a supported JDK (17 or 21), not Java 26 |
| `ANDROID_HOME` | Android SDK root directory | Set by Android Studio; used by Capacitor and Gradle |
| `ANDROID_SDK_ROOT` | Android SDK root (newer alias) | Same value as `ANDROID_HOME`; some tools prefer this name |

Do not hardcode machine-specific paths as project requirements. Each developer's SDK and JDK paths may differ based on their installation.

---

## 8. Emulator Setup

### 8.1 Create a Virtual Device

In Android Studio:

**Tools -> Device Manager -> Create Virtual Device**

1. Choose a device profile (e.g., Pixel 8, Medium Phone).
2. Select a system image with **API 24 or newer**. Prefer a modern stable API image (e.g., API 35 or 36) for current testing.
3. Complete the wizard and create the device.

### 8.2 Start the Emulator

In the Device Manager, click the **Play** button next to the virtual device. Wait for the emulator to boot fully before running the app.

### 8.3 No Devices Warning

If Android Studio shows **"No Devices"** in the toolbar, it means no emulator or physical device is currently selected. This is not an error. Create and start an emulator, or connect a physical device via USB with USB debugging enabled.

---

## 9. Project Validation Commands

Run these commands to verify the environment is set up correctly.

### 9.1 Build and Sync

From the repository root:

```powershell
cd frontend
npm install
npm run build
npx cap sync android
npx cap config
npx cap open android
```

### 9.2 Gradle Validation

From the Android project directory:

```powershell
cd frontend/android
.\gradlew.bat tasks
```

### 9.3 Expected Results

| Command | Expected Result |
| :--- | :--- |
| `npm run build` | Build passes, `dist/index.html` and `dist/assets/` created |
| `npx cap sync android` | Web assets copied to `android/app/src/main/assets/public/`, plugins updated |
| `npx cap config` | Shows `appId: com.yeshmishak.app`, `appName: Yesh Mishak`, `webDir: dist` |
| `npx cap open android` | Android Studio opens the project |
| Android Studio | `app` module visible, `AndroidManifest.xml` opens |
| `.\gradlew.bat tasks` | Task list printed (requires compatible JDK) |

---

## 10. Troubleshooting

### 10.1 `Unsupported class file major version 70`

**Cause:** Java 26 is running Gradle. Gradle 8.14.3 does not support Java 26 (class file major version 70).

**Fix:** Switch the Gradle JDK to a supported version:

- In Android Studio: **File -> Settings -> Build, Execution, Deployment -> Build Tools -> Gradle -> Gradle JDK** -> select Embedded JBR, JDK 21, or JDK 17.
- For terminal: set `JAVA_HOME` to a supported JDK path before running `.\gradlew.bat`.

This issue was confirmed in ISSUE-195 validation.

### 10.2 Android Studio Shows "No Devices"

**Cause:** No emulator or physical device is selected or running.

**Fix:** Open **Tools -> Device Manager**, create a virtual device if none exists, and start it. Or connect a physical Android device via USB with USB debugging enabled in Developer Options.

### 10.3 `dist/index.html` Missing

**Cause:** The web app has not been built yet.

**Fix:** Run `npm run build` from the `frontend/` directory. This creates the `dist/` output that Capacitor copies into the Android project.

### 10.4 `npx cap sync android` Fails

**Possible causes:**

- Dependencies not installed: run `npm install` first.
- Build output missing: run `npm run build` first.
- Wrong directory: run from `frontend/`, not from the repository root.
- Capacitor packages not installed: verify `@capacitor/android` and `@capacitor/core` are in `package.json`.

### 10.5 Android SDK Not Found

**Cause:** `ANDROID_HOME` or `ANDROID_SDK_ROOT` is not set, or the SDK is not installed.

**Fix:** Install the Android SDK through Android Studio SDK Manager (**Tools -> SDK Manager**). Verify environment variables:

```powershell
echo $env:ANDROID_HOME
echo $env:ANDROID_SDK_ROOT
```

If empty, set them to the SDK path shown in Android Studio SDK Manager (usually `C:\Users\<username>\AppData\Local\Android\Sdk` on Windows).

### 10.6 Android Studio Does Not Open the Project

**Cause:** `npx cap open android` may fail if Android Studio is not in the expected path.

**Fix:** Open Android Studio manually, then use **File -> Open** and navigate to `frontend/android/`.

---

## 11. Definition of Done Checklist

Use this checklist to confirm the Android development environment is ready:

- [ ] Android Studio installed (2025.2.1 or newer)
- [ ] Android SDK Platform API 24+ installed
- [ ] Android SDK Build-Tools installed
- [ ] Android SDK Platform-Tools installed
- [ ] Android Emulator installed
- [ ] Emulator created and starts successfully
- [ ] Gradle JDK set to Embedded JBR, JDK 21, or JDK 17 (not Java 26)
- [ ] `JAVA_HOME` points to a compatible JDK
- [ ] `npm run build` passes from `frontend/`
- [ ] `npx cap sync android` passes from `frontend/`
- [ ] Android Studio opens `frontend/android/` and recognizes the project
- [ ] `app` module visible in Android Studio
- [ ] `AndroidManifest.xml` opens in Android Studio
- [ ] `.\gradlew.bat tasks` passes from `frontend/android/`

---

## 12. Related Issues

| Issue | Title | Relevance |
| :--- | :--- | :--- |
| ISSUE-195 | Create Android project using Capacitor | Android project validated; Java 26 Gradle failure discovered |
| ISSUE-196 | Configure Android development environment | This document - environment standardization |
| ISSUE-190 | Capacitor version strategy | Target Capacitor 8.x, version alignment rules |
| ISSUE-189 | React + Vite + Capacitor compatibility audit | Build output and webDir alignment verified |
| ISSUE-187 | Mobile build strategy | Build types, signing expectations, release checklist |
