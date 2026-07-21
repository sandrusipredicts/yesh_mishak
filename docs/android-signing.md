# Android Release Signing

**Roadmap task:** E10-01

**Scope:** Local release-signing setup; no keystore or credential is stored in this repository

## Overview

Android release builds use a `release` signing configuration in `frontend/android/app/build.gradle`. The configuration reads four values from the ignored local file `frontend/android/key.properties`. Debug builds keep their existing behavior: local debug builds use the Android default debug key, while CI may supply its dedicated debug keystore through the existing `ANDROID_DEBUG_KEYSTORE_*` environment variables.

The repository contains only `frontend/android/key.properties.example`. It does not contain a release keystore, passwords, aliases, or other signing secrets.

## 1. Generate the release keystore

Choose an organization-controlled machine with a supported JDK and run `keytool`. Replace the angle-bracket placeholders; do not add passwords to the command because `keytool` will prompt for them securely.

```text
keytool -genkeypair -v -keystore <secure-directory>/yesh-mishak-release.jks -keyalg RSA -keysize 2048 -validity 10000 -alias <release-key-alias>
```

Record the keystore password, key alias, and key password in the organization's approved password or secrets manager. The keystore is required to publish updates signed with the same key, so create an encrypted backup and test its recovery process. Never send the keystore or passwords through chat, email, issue comments, or pull requests.

This command is an operator step. E10-01 does not run it and does not generate a real keystore.

## 2. Store the keystore

Store the `.jks` outside the Git checkout in an access-controlled, encrypted location. Grant access only to release maintainers and keep a separate encrypted backup under organizational control. Do not place the only copy on a developer laptop.

The root and Android `.gitignore` files exclude `key.properties`, `*.jks`, and `*.keystore` as a defense against accidental commits. Ignore rules are not a substitute for secure custody.

## 3. Create `key.properties`

From the repository root, copy the template without editing the tracked example:

```powershell
Copy-Item frontend/android/key.properties.example frontend/android/key.properties
```

Edit `frontend/android/key.properties` and replace every placeholder:

```properties
storeFile=<absolute-path-to-release-keystore>
storePassword=<keystore-password>
keyAlias=<release-key-alias>
keyPassword=<key-password>
```

`storeFile` may be absolute or relative to `frontend/android`, but an absolute path to a location outside the repository is recommended. In Java properties files on Windows, use forward slashes or escape each backslash. Do not quote values unless the quote character is part of the actual value.

Confirm that representative local signing files are ignored:

```powershell
git check-ignore -v --no-index frontend/android/key.properties frontend/android/example-release.jks frontend/android/example-release.keystore
```

The preferred external keystore location will not appear in Git at all.

## 4. Prepare the Android project

Before a release build, provide the production web configuration and the Firebase Android client file for `com.yeshmishak.app`, then build and sync the Capacitor assets according to the existing Android setup documentation:

```powershell
Set-Location frontend
npm ci
npm run build:android
npx cap sync android
```

`frontend/android/app/google-services.json` is also ignored and must be supplied through the approved local or CI secret workflow.

## 5. Build a signed release

Build the Google Play App Bundle from the Android project directory:

```powershell
Set-Location frontend/android
.\gradlew.bat bundleRelease --no-daemon
```

On macOS or Linux, use `./gradlew bundleRelease --no-daemon`. The signed bundle is written to:

```text
frontend/android/app/build/outputs/bundle/release/app-release.aab
```

For a signed APK used by an approved non-Play distribution workflow, run `assembleRelease`; its output is under `frontend/android/app/build/outputs/apk/release/`.

Gradle fails artifact-producing release tasks when `key.properties` is absent, when a required property is blank, or when the configured keystore file does not exist. It does not fall back to an unsigned or debug-signed release. Debug, lint, and unit-test tasks do not require `key.properties` unless they also request a release artifact.

## 6. Verify the signed artifact

Before distribution, verify the bundle and record its certificate fingerprints without exposing passwords:

```text
jarsigner -verify -verbose -certs frontend/android/app/build/outputs/bundle/release/app-release.aab
keytool -list -v -keystore <secure-directory>/yesh-mishak-release.jks -alias <release-key-alias>
```

Compare the SHA-1 and SHA-256 fingerprints with the approved release records and with the Android OAuth/Firebase configuration. Never assume release fingerprints match the debug certificate.

## 7. CI and rotation boundaries

This change does not add production signing material to CI and does not alter the existing CI debug signing variables. A future protected release workflow should materialize the keystore only for the duration of an approved release job, source all four values from protected secrets, restrict logs and artifacts, and remove temporary signing files in an `always()` cleanup step.

If the key may be compromised, stop releases, notify the security and release owners, preserve audit evidence, and follow Google Play's signing-key recovery or upgrade process as applicable. Do not silently create a replacement key: changing keys without an approved migration can prevent existing users from receiving updates.

## Related documentation

- `docs/android-development-environment.md`
- `docs/android-firebase-configuration.md`
- `docs/android-google-authentication-configuration.md`
- `docs/mobile-build-strategy.md`
- `docs/release-checklist-template.md`
