# E10-09 — Establish crash-free-rate baseline plan

This document establishes the plan for verifying the Android crash-free-rate baseline before the public release of the "יש משחק?" application.

## 1. Approved Architectural Direction

We will implement a read-only Gradle metadata task combined with a Node orchestration script. This preserves `build.gradle` as the authoritative source of truth for Android versioning, eliminating the need for a separate JSON version file or fragile regex parsing.

The intended execution flow is:
```text
Gradle resolves applicationId, versionName, and versionCode
→ Gradle task prints canonical JSON
→ Node script parses and validates the JSON
→ Node supplies canonical release/dist to Vite via process execution
→ Vite builds the web bundle
→ Capacitor sync copies the current bundle
→ Gradle builds the Android artifact
```

---

## 2. Exact Implementation Design

### 2.1 Gradle Metadata Task
A read-only task will be added to `frontend/android/app/build.gradle` that evaluates the active Android configuration and outputs a unique, machine-readable JSON record to `stdout`.
*   It will evaluate the Android DSL properties (`applicationId`, `versionName`, `versionCode`).
*   It will not mutate files or change version variables.
*   It will use a unique prefix/suffix to allow reliable extraction despite Gradle daemon logging.
*   It will support the active release variant and work across OS environments.

Example output:
```text
===SENTRY_METADATA_START===
{
  "applicationId": "com.yeshmishak.app",
  "versionName": "1.0.4",
  "versionCode": 5,
  "release": "com.yeshmishak.app@1.0.4+5",
  "dist": "5"
}
===SENTRY_METADATA_END===
```

### 2.2 Node Metadata Resolver
A Node orchestration script (`frontend/scripts/build-android-release.mjs`) will:
1.  Execute the Gradle metadata task (`gradlew.bat` on Windows).
2.  Extract the JSON record using the unique marker.
3.  Perform strict validation:
    *   `applicationId` must equal `com.yeshmishak.app`
    *   `versionName` must match the repository’s accepted semantic version pattern
    *   `versionCode` must be a positive integer
    *   `release` must exactly equal `applicationId@versionName+versionCode`
    *   `dist` must exactly equal the string form of `versionCode`
4.  Exit non-zero with a clear error if validation fails.
5.  Launch the Vite build process, explicitly setting `VITE_SENTRY_RELEASE` and `VITE_SENTRY_DIST` in its environment.
6.  Ensure no generated metadata is committed or left polluting the environment on failure.

### 2.3 Build Scripts
`package.json` will be updated with explicit, deterministic commands:
```json
"scripts": {
  "build:android:web": "vite build --mode android",
  "build:android:sync": "npx cap sync android",
  "build:android:verify": "node scripts/verify-android-build.mjs",
  "build:android:local-release": "node scripts/build-android-release.mjs --local",
  "build:android:official-release": "node scripts/build-android-release.mjs --official"
}
```
The official release pipeline will orchestrate:
`resolve metadata` → `Vite build` → `verify bundle` → `Capacitor sync` → `verify copied assets` → `Gradle bundleRelease`.

### 2.4 Vite Injection
Vite will natively consume `process.env.VITE_SENTRY_RELEASE` and `process.env.VITE_SENTRY_DIST` provided by the orchestration script.
*   Vite will inject these into the client bundle via `define` or `import.meta.env`.
*   These exact environment variables will configure the `@sentry/vite-plugin` to align source maps with the canonical release.

---

## 3. Environment Behaviors

### 3.1 Local Android Build (`build:android:local-release`)
*   **Source maps**: May succeed without `SENTRY_AUTH_TOKEN`.
*   **Warning**: Must clearly report to the developer that source-map upload was skipped.
*   **Metadata**: Must still successfully extract and embed the valid canonical release and dist into the web assets.

### 3.2 Official Play Release (`build:android:official-release`)
*   **Fail-fast requirements**: The pipeline MUST fail if any of the following are missing:
    *   `SENTRY_AUTH_TOKEN`
    *   Sentry org (`SENTRY_ORG`)
    *   Sentry project (`SENTRY_MOBILE_PROJECT`)
    *   Canonical `release`
    *   Canonical `dist`
*   **Source-map upload**: Must fail non-zero if the upload fails.
*   **Evidence**: Must generate a machine-readable output or CI evidence explicitly recording the exact release and dist string used.

---

## 4. Post-Build Verification

The post-build verification script (`scripts/verify-android-build.mjs`) will perform targeted, dynamic validation rather than broad text searches. It will:
1.  Read the final built Javascript chunks in `frontend/dist`.
2.  Dynamically confirm that the expected canonical `release` and `dist` strings (as retrieved from Gradle) are present in the JS bundle.
3.  Confirm that the old `'unknown'` fallback is entirely absent from the monitoring initialization paths.
4.  Compute and compare hashes between the built Vite assets (`frontend/dist`) and the copied Capacitor assets (`frontend/android/app/src/main/assets/public`) to guarantee they are perfectly synced.
5.  Exit non-zero if any mismatch is found.

---

## 5. Manual Owner Steps

Pressing "Build" or "Run" inside Android Studio **does not** automatically rebuild the Vite web bundle. If a developer bumps `versionName` or changes JS code, they must manually execute:
```bash
npm run build:android:local-release
```
before building the native app in Android Studio.

---

## 6. Files Expected to Change

*   `frontend/android/app/build.gradle`: Addition of the read-only JSON metadata task.
*   `frontend/scripts/build-android-release.mjs`: New orchestration script.
*   `frontend/scripts/verify-android-build.mjs`: New targeted bundle verification script.
*   `frontend/package.json`: NPM script additions.
*   `frontend/vite.config.js`: Sentry environment parsing and plugin alignment.
*   `frontend/src/monitoring/config.js`: Consumption of the canonical environment variables.
*   `.github/workflows/android-build-validation.yml`: Adoption of the new `official-release` flow.

---

## 7. Acceptance Criteria

- [x] Sentry monitoring audit and existing configuration analyzed.
- [x] Build order flaw analyzed and Orchestration architectural design explicitly approved.
- [x] Gradle JSON metadata read-only task implemented and tested on Windows.
- [x] Node orchestration script implemented with environment variable injection.
- [x] Targeted post-build bundle and Capacitor hash verification implemented.
- [x] Release metadata correctly resolved without `unknown` grouping.
- [x] Planned verification test suite passed.
- [~] Automated regression checks passed; manual Android flow verification remains.
- [~] Native crash capture verified under the canonical production-like release.
- [~] Authenticated source-map upload verified.
- [~] Manual crash event verified on the physical Android device.
- [ ] Sentry Release Health and session recording verified.
- [ ] Google Play Android Vitals compared with Sentry.
- [ ] Latest Google Play versionName/versionCode manually confirmed.
- [ ] Android crash-free rate baseline established.
