# Android Project Structure Audit

## Summary

The Android project structure is coherent, buildable, and aligned with the approved application identifier `com.yeshmishak.app`. Capacitor configuration, Android Gradle configuration, the native source package, generated runtime configuration, and packaged web assets agree.

The required frontend build, Capacitor synchronization, Capacitor configuration inspection, Gradle project inspection, and Android debug build all passed on 2026-07-01. No structural blocker was found for upcoming native feature work.

The audit is based on branch `issue-198-validate-android-project-structure`, created from updated `main` at `d40570f` after ISSUE-197 was merged.

## Project Context

| Item | Location or value |
| --- | --- |
| Repository frontend root | `frontend/` |
| Capacitor configuration | `frontend/capacitor.config.ts` |
| Android project root | `frontend/android/` |
| Android app module | `frontend/android/app/` |
| Approved application ID | `com.yeshmishak.app` |
| Capacitor version family | 8.x |
| Android build output | `frontend/android/app/build/outputs/apk/debug/app-debug.apk` |

The Android platform is checked into the repository, while build outputs and synchronized web assets are generated locally.

## Source Structure

### Production sources

The production Java source root is:

```text
frontend/android/app/src/main/java/
```

`MainActivity` is located at:

```text
frontend/android/app/src/main/java/com/yeshmishak/app/MainActivity.java
```

Its declaration is:

```java
package com.yeshmishak.app;
```

The directory path and package declaration align with the approved package identifier. `MainActivity` extends Capacitor's `BridgeActivity` and contains no custom native behavior yet.

No Kotlin production source directory or Kotlin production source file is currently present. New Java or Kotlin native code should follow the `com/yeshmishak/app` package path.

### Test sources

The project contains the standard Android test roots:

```text
frontend/android/app/src/test/java/
frontend/android/app/src/androidTest/java/
```

The template test classes remain under the Java package `com.getcapacitor.myapp`. These test-class namespaces do not control the production application ID. The instrumentation test correctly asserts that the target application package is `com.yeshmishak.app`, as resolved in ISSUE-197.

`com.getcapacitor.BridgeActivity` in `MainActivity` is a valid Capacitor framework import, not a stale application package.

### Legacy package assessment

- Production configuration and source contain no stale `com.getcapacitor.app` or `com.getcapacitor.myapp` application identifier.
- The two template test-class namespaces still use `com.getcapacitor.myapp`. This is cosmetic test-source legacy naming and does not affect application packaging.
- The production package path, Gradle namespace, application ID, Capacitor app ID, and Android string resources all use `com.yeshmishak.app`.

## Assets

The frontend build writes web assets to:

```text
frontend/dist/
```

`capacitor.config.ts` sets `webDir` to `dist`. Running `npx cap sync android` copies those assets to:

```text
frontend/android/app/src/main/assets/public/
```

The same sync generates:

```text
frontend/android/app/src/main/assets/capacitor.config.json
```

The generated JSON was inspected and contains:

| Key | Value |
| --- | --- |
| `appId` | `com.yeshmishak.app` |
| `appName` | `Yesh Mishak` |
| `webDir` | `dist` |

Both the Android `public/` assets and generated `capacitor.config.json` are excluded by `frontend/android/.gitignore`. `frontend/dist/` is excluded by `frontend/.gitignore`.

These files are generated artifacts. They should be regenerated through `npm run build` and `npx cap sync android`, not edited manually.

## Gradle

### Gradle files

Root Android Gradle files:

```text
frontend/android/build.gradle
frontend/android/settings.gradle
frontend/android/variables.gradle
frontend/android/gradle.properties
frontend/android/gradle/wrapper/gradle-wrapper.properties
```

App and Capacitor integration files:

```text
frontend/android/app/build.gradle
frontend/android/app/capacitor.build.gradle
frontend/android/capacitor.settings.gradle
```

`capacitor.build.gradle` and `capacitor.settings.gradle` explicitly identify themselves as generated files. Capacitor synchronization owns their plugin entries and Java compile options.

### Toolchain and SDK versions

| Setting | Value |
| --- | --- |
| Gradle wrapper | 8.14.3 |
| Android Gradle Plugin | 8.13.0 |
| Google Services Gradle plugin | 4.4.4 |
| Java source/target compatibility | Java 21 |
| `compileSdk` | 36 |
| `targetSdk` | 36 |
| `minSdk` | 24 |
| `namespace` | `com.yeshmishak.app` |
| `applicationId` | `com.yeshmishak.app` |
| `versionCode` | 1 |
| `versionName` | 1.0 |

The command-line build must use a compatible JDK. Android Studio's bundled Java 21 JBR passed. The machine's default Java 26 runtime is not compatible with the Android `JdkImageTransform` step and should not be used for Gradle.

### Project and dependency structure

`gradlew projects` reports:

```text
:app
:capacitor-android
:capacitor-cordova-android-plugins
:capacitor-push-notifications
```

The app module depends on:

- Capacitor Android.
- The generated Capacitor/Cordova plugin bridge.
- AndroidX AppCompat.
- AndroidX CoordinatorLayout.
- AndroidX Core SplashScreen.
- JUnit for local tests.
- AndroidX JUnit and Espresso for instrumentation tests.

Capacitor synchronization adds the installed Push Notifications plugin to the generated settings and app dependency files.

The app Gradle script conditionally applies the Google Services plugin when `frontend/android/app/google-services.json` exists. That file was not present in the audited checkout. Push notification builds can still compile, but functional Firebase push setup requires the environment-specific file to be supplied through the project's secure configuration process.

### Gradle observations

- The required `assembleDebug` task passes.
- Gradle warns that `flatDir` repositories do not support metadata. This is inherited from the generated Capacitor/Cordova bridge and is non-blocking.
- A known instrumentation-test dependency conflict exists between Kotlin standard-library artifacts. It is documented under Known Issues and is not part of the production debug APK path.

## Manifest

The application manifest is:

```text
frontend/android/app/src/main/AndroidManifest.xml
```

### Package ownership

The manifest intentionally has no `package` attribute. With the current Android Gradle Plugin, `namespace` and `applicationId` in `app/build.gradle` own package configuration. Adding a manifest package attribute would be unnecessary and potentially misleading.

### Permissions

The manifest declares:

```text
android.permission.INTERNET
android.permission.POST_NOTIFICATIONS
```

`INTERNET` supports the Capacitor web application and API traffic. `POST_NOTIFICATIONS` supports notification permission on Android 13 and newer.

### Activities and intent filters

`MainActivity` is declared with:

- Relative class name `.MainActivity`, resolved against `com.yeshmishak.app`.
- `launchMode="singleTask"`.
- `exported="true"`.
- Capacitor's expected configuration-change handling.
- The launcher `MAIN` action and `LAUNCHER` category.

The activity must be exported because it has a launcher intent filter. This is correct for current Android requirements.

No custom deep-link or app-link intent filter is present on updated `main` at the time of this audit. Any future deep-link capability must add a narrowly scoped browsable intent filter and validate its interaction with `singleTask` and Capacitor app URL events.

### Provider

The AndroidX `FileProvider` authority uses:

```text
${applicationId}.fileprovider
```

This correctly follows the configured application ID without duplicating it in the manifest. The provider is not exported and grants URI permissions only when required.

### Native capability implications

Future native capabilities may require:

- New runtime and manifest permissions.
- New Capacitor plugin dependencies.
- Service, receiver, provider, or activity declarations.
- Deep-link intent filters.
- ProGuard/R8 rules for release builds.

Such changes should be made in source configuration where possible. Files marked as Capacitor-generated should continue to be updated through `npx cap sync android`.

## Capacitor Integration

`frontend/capacitor.config.ts` defines:

| Setting | Value |
| --- | --- |
| `appId` | `com.yeshmishak.app` |
| `appName` | `Yesh Mishak` |
| `webDir` | `dist` |

The Android platform is present at `frontend/android/`.

Installed Capacitor packages are:

| Package | Declared version |
| --- | --- |
| `@capacitor/android` | `^8.4.1` |
| `@capacitor/core` | `^8.4.1` |
| `@capacitor/cli` | `^8.4.1` |
| `@capacitor/push-notifications` | `^8.1.1` |

During validation, Capacitor detected `@capacitor/push-notifications@8.1.1` as the installed Android plugin.

The generated integration consists of:

- `android/app/src/main/assets/public/` for synchronized web content.
- `android/app/src/main/assets/capacitor.config.json` for runtime configuration.
- `android/capacitor.settings.gradle` for Capacitor module inclusion.
- `android/app/capacitor.build.gradle` for plugin dependencies and Java compatibility.
- `android/capacitor-cordova-android-plugins/` for the generated Cordova compatibility bridge.

Capacitor configuration and Android Gradle configuration agree on `com.yeshmishak.app`. The generated runtime config also contains the same app ID.

## Validation Results

Validation was performed on 2026-07-01 from branch `issue-198-validate-android-project-structure`.

| Command | Result | Notes |
| --- | --- | --- |
| `git status` | PASS | Clean before report creation. |
| `npm run build` from `frontend/` | PASS | Vite transformed 1,916 modules and produced `dist/`. |
| `npx cap sync android` from `frontend/` | PASS | Copied `dist` assets, generated `capacitor.config.json`, and detected Push Notifications. |
| `npx cap config` from `frontend/` | PASS | Reported `appId=com.yeshmishak.app`, `appName=Yesh Mishak`, and `webDir=dist`. |
| `.\gradlew.bat assembleDebug` from `frontend/android/` | PASS | Completed 125 tasks under Android Studio's Java 21 JBR. |
| `.\gradlew.bat projects` from `frontend/android/` | PASS | Reported the app, Capacitor Android, Cordova bridge, and Push Notifications projects. |

The debug APK build passed. Java 21 was selected for Gradle because the machine default Java 26 runtime is outside the supported project toolchain.

## Known Issues

### Blocker

None identified.

### Non-blocking

1. **Instrumentation test Kotlin standard-library conflict**
   - An additional instrumentation APK build during ISSUE-197 compiled the app instrumentation test, then failed in `:capacitor-cordova-android-plugins:checkDebugAndroidTestDuplicateClasses`.
   - The conflict involved `kotlin-stdlib:1.8.22` and older `kotlin-stdlib-jdk7`/`kotlin-stdlib-jdk8:1.6.21` artifacts.
   - This does not affect `assembleDebug`, which passes.
   - The dependency alignment fix is intentionally excluded from ISSUE-198 and should be tracked separately.

2. **Java 26 is incompatible with the current Android build path**
   - The default system Java 26 runtime fails during Android `JdkImageTransform`.
   - Android Studio's bundled Java 21 JBR passes.
   - This is an environment/toolchain requirement rather than a project-structure defect.

3. **`flatDir` repository warning**
   - Gradle warns that flat directory repositories do not provide dependency metadata.
   - This comes from the Capacitor/Cordova bridge configuration and does not block the debug build.

### Future cleanup

1. **Template test package names**
   - Local and instrumentation test classes remain under `com.getcapacitor.myapp`.
   - Their package names do not affect the production application ID.
   - They may be renamed in a dedicated test cleanup issue if consistent naming becomes valuable.

2. **Push notification environment configuration**
   - `google-services.json` was not present in the audited checkout.
   - Secure environment-specific provisioning is required before validating Firebase push behavior.

### Already resolved

1. **Android application identifier alignment**
   - ISSUE-197 aligned and verified `com.yeshmishak.app`.
   - Capacitor app ID, Gradle namespace, Gradle application ID, native source path/package, Android string resources, generated config, and instrumentation target assertion now agree.

## Risk Assessment

| Area | Risk | Assessment |
| --- | --- | --- |
| Package identity | Low | All production package identifiers agree. |
| Source layout | Low | MainActivity path and package are aligned; no custom native code complexity exists yet. |
| Asset synchronization | Low | Build and sync paths are explicit, generated, ignored, and validated. |
| Gradle build | Low | Debug APK builds successfully with Java 21. |
| Manifest | Low | Launcher export and provider authority are correct; permissions are limited to current capabilities. |
| Capacitor plugins | Low | Plugin registration is generated and sync is reproducible. |
| Instrumentation tests | Medium | Separate Kotlin dependency conflict prevents full instrumentation APK assembly. |
| Push configuration | Medium | Plugin is installed, but environment-specific Google Services configuration was absent. |

The current production Android structure is low risk for incremental native feature work. Each new capability should still receive an explicit manifest, permission, lifecycle, and plugin-registration review.

## Recommendations

1. Use Android Studio's bundled Java 21 JBR for IDE and command-line Gradle builds.
2. Continue the build sequence `npm run build` followed by `npx cap sync android` before Android packaging.
3. Do not manually edit synchronized web assets, generated `capacitor.config.json`, `capacitor.settings.gradle`, or `app/capacitor.build.gradle`.
4. Track the instrumentation Kotlin dependency conflict in a separate issue before relying on connected Android tests in CI.
5. Provision `google-services.json` through the approved secure environment process before push notification validation.
6. For each native capability, document required permissions, exported components, intent filters, background behavior, and Android-version constraints.
7. Keep application code under `com.yeshmishak.app` and preserve agreement between Capacitor `appId`, Gradle `namespace`, and Gradle `applicationId`.

## Final Verdict

**GO**

The Android project structure is safe for upcoming native features. No structural change is required before native work begins.

The following items should be tracked separately and do not block the current production debug build:

- Kotlin standard-library alignment for instrumentation APK builds.
- Optional cleanup of legacy template test package names.
- Secure provisioning and functional validation of Google Services configuration for push notifications.
