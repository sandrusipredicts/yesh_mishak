# Android Firebase Configuration

This project uses Capacitor for Android and keeps the Android application ID fixed at:

```text
com.yeshmishak.app
```

Native Android push notifications require Firebase Android configuration at:

```text
frontend/android/app/google-services.json
```

This file is project-specific Firebase client configuration. It is not a Firebase service-account private key, but it must still be handled deliberately so local, CI, and release builds do not accidentally use the wrong Firebase project.

## Repository Policy

- `frontend/android/app/google-services.json` is ignored by Git and must not be committed.
- Backend Firebase service-account JSON must never be used as `google-services.json`.
- The file must contain an Android client for `com.yeshmishak.app`.
- There are no Android product flavors today, so debug and release builds use the same Android app configuration unless a future issue adds explicit environment separation.

## Firebase Console Owner Steps

1. Open the correct Firebase project.
2. Register or verify the Android app package name:

   ```text
   com.yeshmishak.app
   ```

3. Download the current Android `google-services.json`.
4. Place it locally at:

   ```text
   frontend/android/app/google-services.json
   ```

5. Validate it before building:

   ```bash
   cd frontend
   npm run android:google-services:validate
   ```

6. For CI, Base64-encode the complete file content and create a repository-level
   GitHub Actions secret under **Settings > Secrets and variables > Actions**:

   ```text
   ANDROID_GOOGLE_SERVICES_JSON_BASE64
   ```

7. Allow the secret to be read by the manually dispatched
   `Android Build Validation` workflow, then run that workflow from the Actions tab.
8. Confirm the materialization step and cleanup complete without configuration
   content appearing in the logs.
9. Never paste or commit the decoded JSON into source files, docs, logs, or issue comments.

## Local Development

After `frontend/android/app/google-services.json` is present and validated:

```bash
cd frontend
npm run build:android
npx cap sync android
cd android
./gradlew assembleDebug
```

On Windows PowerShell, use:

```powershell
cd frontend
npm run build:android
npx cap sync android
cd android
.\gradlew.bat assembleDebug
```

The Gradle build now fails early if `frontend/android/app/google-services.json` is missing or empty. This prevents building an Android APK that silently lacks Firebase-generated resources.

## CI Materialization

`.github/workflows/android-build-validation.yml` provides two paths:

- Pull requests run the synthetic validator test suite without reading any secret.
  This includes pull requests from forks.
- A trusted maintainer can use `workflow_dispatch` to materialize the real config,
  build the debug APK, upload only the APK artifact, and remove the generated JSON
  in an `always()` cleanup step. A missing secret fails at materialization before
  Gradle runs.

The trusted build runs the following sequence:

```bash
cd frontend
npm run android:google-services
npm run build:android
npx cap sync android
cd android
./gradlew assembleDebug
```

The materialization command reads `ANDROID_GOOGLE_SERVICES_JSON_BASE64`, decodes it, validates that the JSON contains an Android client for `com.yeshmishak.app`, and writes:

```text
frontend/android/app/google-services.json
```

It fails without printing Firebase project values when:

- the secret is missing,
- the Base64 value is malformed,
- the decoded content is invalid JSON,
- the file does not contain `com.yeshmishak.app`.

## Encoding Examples

Bash:

```bash
base64 -w 0 frontend/android/app/google-services.json
```

Windows PowerShell:

```powershell
[Convert]::ToBase64String(
    [System.IO.File]::ReadAllBytes(
        "frontend\android\app\google-services.json"
    )
) | Set-Clipboard
```

Store only the encoded output in the CI secret. Do not commit the encoded value.

macOS Bash or zsh:

```bash
base64 < frontend/android/app/google-services.json | tr -d '\n'
```

## Rotation And Updates

Replace and revalidate `google-services.json` when:

- the Firebase Android app configuration changes,
- the project migrates to another Firebase project,
- `com.yeshmishak.app` is re-registered,
- debug and release builds are intentionally separated,
- the downloaded file was generated for the wrong package,
- Firebase Console indicates the Android app config has changed.

## Manual Device Verification

Build-time validation does not prove runtime FCM delivery. After obtaining the real Firebase file:

1. Run `npm run android:google-services:validate`.
2. Run `npm run build:android`.
3. Run `npx cap sync android`.
4. Build and install the debug APK on the Samsung Galaxy S24 Ultra.
5. Open the app and sign in.
6. Accept Android notification permission if prompted.
7. Confirm native Firebase initialization does not log missing-config errors.
8. Confirm an FCM token is generated and registered through the existing app flow.
9. Trigger a real push notification from the existing backend flow.
10. Confirm receipt while the app is foregrounded, backgrounded, and closed where Android permits.
11. Recheck login, Google Sign-In, App Links, map loading, and session restoration.
