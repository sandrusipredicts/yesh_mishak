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

### GitHub Actions configuration

Create these repository variables under **Settings > Secrets and variables >
Actions > Variables** before manually dispatching the workflow:

| Repository variable | Required | Source | Android purpose |
| --- | --- | --- | --- |
| `VITE_API_URL` | Yes | The HTTPS base URL of the deployed FastAPI backend, matching the existing Vercel `VITE_API_URL` convention | Baked into the Vite bundle so API, login, map, game, and notification requests reach the backend |
| `VITE_GOOGLE_CLIENT_ID` | Yes | The existing Web OAuth client ID in Google Cloud Console; it must match the backend `GOOGLE_CLIENT_ID` audience | Used as the native Google Sign-In `serverClientId` |

These values are public client configuration embedded in the APK, so repository
variables are appropriate; putting them in Actions secrets would not make them
secret after the Vite build. The workflow validates that both values are present
without printing them, and also requires `VITE_API_URL` to use HTTPS because the
Capacitor Android WebView blocks plain-HTTP API calls.

Create this repository secret under **Settings > Secrets and variables > Actions
> Secrets**:

| Repository secret | Required | Source | Android purpose |
| --- | --- | --- | --- |
| `ANDROID_GOOGLE_SERVICES_JSON_BASE64` | Yes | Base64 encoding of the Firebase Android app's `google-services.json` for `com.yeshmishak.app` | Materialized and package-validated before the native build, then deleted during cleanup |
| `ANDROID_DEBUG_KEYSTORE_BASE64` | Yes | Base64 encoding of the dedicated non-production debug/test keystore | Gives every CI validation APK the same signing certificate |
| `ANDROID_DEBUG_KEYSTORE_PASSWORD` | Yes | Password for that test keystore | Supplied to Gradle without entering source control or logs |
| `ANDROID_DEBUG_KEY_ALIAS` | Yes | Alias of the signing key inside that test keystore | Selects the stable test certificate |
| `ANDROID_DEBUG_KEY_PASSWORD` | Yes | Password for that signing-key alias | Supplied to Gradle without entering source control or logs |

The four debug-signing secrets are a unit: if any is missing, the workflow fails
before building. Never use the Play Store production signing key for this debug
validation workflow. The decoded file is written only to the ignored
`frontend/android/ci-debug.keystore` path and removed in the workflow's
`always()` cleanup step together with `google-services.json`.

The selected stable test certificate currently has these public fingerprints:

```text
SHA-1:   8A:CD:E8:33:7C:67:73:D8:30:34:37:8C:FF:61:7F:C6:FE:53:32:4D
SHA-256: 40:38:5F:E6:9C:B4:6F:3B:79:C0:4D:10:24:3B:61:03:50:57:91:99:CF:24:46:E7:48:20:77:D8:65:02:52:38
```

The workflow independently extracts the certificate from the completed APK and
prints only its SHA-1 and SHA-256 digests before uploading the APK.

The frontend also references `VITE_FIREBASE_API_KEY`,
`VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`,
`VITE_FIREBASE_STORAGE_BUCKET`, `VITE_FIREBASE_MESSAGING_SENDER_ID`,
`VITE_FIREBASE_APP_ID`, and `VITE_FIREBASE_VAPID_KEY` for browser Web Push.
They are not required by the Android APK's Capacitor Push Notifications path,
which uses the native Firebase configuration above, so the Android workflow does
not require or inject them. `VITE_SHOW_TEST_PUSH` is development-only and is not
enabled in the production-mode Android build. `VITE_API_BASE_URL` remains a
legacy fallback; new CI configuration uses canonical `VITE_API_URL` only.

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

For the dedicated test keystore on Windows PowerShell, run this locally and put
the clipboard value into `ANDROID_DEBUG_KEYSTORE_BASE64`:

```powershell
[Convert]::ToBase64String(
    [System.IO.File]::ReadAllBytes(
        "$env:USERPROFILE\.android\debug.keystore"
    )
) | Set-Clipboard
```

Create the other three signing secrets from that same keystore's credentials.
Do not paste any of the four values into logs, documentation, issues, or chat.

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
