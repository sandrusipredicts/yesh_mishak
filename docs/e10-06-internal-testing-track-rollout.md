# E10-06 — Internal Testing Track Rollout

**Roadmap task:** E10-06 — Set up internal testing track rollout

**Scope:** Documentation, checklists, and validation scripts for the Google Play internal testing track. No application code changes. No Play Console actions are performed by this task — all console operations are documented for the release owner.

## 1. Purpose

This document guides the release owner through uploading the first signed Android App Bundle to the Google Play internal testing track, configuring testers, verifying the installed build, and collecting feedback before any wider distribution. It assumes E10-01 through E10-05 are complete.

## 2. Prerequisites

Every prerequisite must be confirmed before proceeding. A missing item is a hard stop.

| # | Prerequisite | Verification | Reference |
| :--- | :--- | :--- | :--- |
| 1 | Google Play Console developer account is verified and active | Log in to Play Console; account status shows "Active" | [E10-03 enrollment plan](https://github.com/sandrusipredicts/yesh_mishak/issues/878) |
| 2 | Play Console app exists for `com.yeshmishak.app` | App visible in Play Console dashboard | [E10-03 enrollment plan](https://github.com/sandrusipredicts/yesh_mishak/issues/878) |
| 3 | Play App Signing is enrolled | Play Console > Setup > App signing shows enrolled status | [Android signing docs](android-signing.md) |
| 4 | Release keystore generated and securely stored | `key.properties` populated, `gradlew bundleRelease` succeeds | [Android signing docs](android-signing.md) |
| 5 | Production `google-services.json` available | File exists at `frontend/android/app/google-services.json` for `com.yeshmishak.app` | [Android Firebase configuration](android-firebase-configuration.md) |
| 6 | Google OAuth consent screen published to Production | Google Cloud Console > APIs & Services > OAuth consent screen shows "Published" | [Android Google auth configuration](android-google-authentication-configuration.md) |
| 7 | Play app-signing certificate SHA-256 registered in Firebase and OAuth | Firebase console shows Play signing certificate; OAuth client includes Play fingerprint | [Android signing docs](android-signing.md) §6 |
| 8 | Store listing assets uploaded to Play Console | Play Console > Store listing shows approved icon, feature graphic, screenshots, and copy | [E10-04 runbook](e10-04-google-play-store-listing-runbook.md) |
| 9 | Privacy policy URL accessible without login | `https://yesh-mishak.com/privacy` loads correctly from a logged-out browser | [E10-02 legal pages](../frontend/src/pages/PublicPolicyPage.jsx) |
| 10 | versionCode=1 and versionName="1.0.0" confirmed | `cd frontend/android && gradlew :app:printVersion` outputs correct values | [E10-05 version strategy](e10-05-android-version-strategy.md) |
| 11 | App Content declarations complete in Play Console | Play Console > Policy > App content shows all items completed | [E10-04 declarations](../release/google-play/declarations/) |
| 12 | Digital Asset Links updated with Play signing certificate | `https://yesh-mishak.com/.well-known/assetlinks.json` contains Play app-signing SHA-256 | [App Links configuration](android-app-links-configuration.md) |

## 3. Build the release AAB

Follow the exact sequence from [android-signing.md](android-signing.md). Do not skip or reorder steps.

```powershell
# 1. Clean checkout on the release commit
Set-Location C:\Users\orel1\yesh_mishak
git checkout main
git pull origin main
git status  # must be clean

# 2. Install dependencies and build web assets
Set-Location frontend
npm ci
npm run build:android

# 3. Sync Capacitor
npx cap sync android

# 4. Verify version before building
Set-Location android
.\gradlew.bat :app:printVersion --no-daemon
# Confirm: versionCode=1, versionName=1.0.0

# 5. Build the signed release AAB
.\gradlew.bat bundleRelease --no-daemon

# 6. Verify the signed artifact
jarsigner -verify -verbose -certs app\build\outputs\bundle\release\app-release.aab
```

The signed AAB is at: `frontend/android/app/build/outputs/bundle/release/app-release.aab`

Record the SHA-256 hash of the AAB for traceability:

```powershell
Get-FileHash frontend\android\app\build\outputs\bundle\release\app-release.aab -Algorithm SHA256
```

## 4. Pre-upload validation checklist

Complete every item before uploading to Play Console. Any failure is a hard stop.

- [ ] `gradlew :app:printVersion` shows versionCode=1, versionName=1.0.0
- [ ] `jarsigner -verify` passes with no warnings
- [ ] Certificate fingerprints match the registered upload key
- [ ] AAB file size is reasonable (expected: ~10–12 MB)
- [ ] `git status` is clean on the release commit
- [ ] `git log --oneline -1` matches the intended release commit
- [ ] No secrets in the built web bundle (`frontend/dist/`)
- [ ] `npm run lint` passes
- [ ] `npm run build:android` succeeds without errors
- [ ] Frontend asset validation scripts pass: `npm run android:version:validate`
- [ ] Play Store asset validation passes: `.\release\scripts\validate-google-play-assets.ps1`
- [ ] Privacy policy page loads at the public URL without authentication
- [ ] No `key.properties`, `.jks`, or `.keystore` file is tracked in Git

## 5. Upload to internal testing track

These steps are performed by the release owner inside Google Play Console. They cannot be automated from the repository.

### 5.1 Navigate to the internal testing track

1. Open [Google Play Console](https://play.google.com/console).
2. Select the **Yesh Mishak** app (`com.yeshmishak.app`).
3. Navigate to **Release** > **Testing** > **Internal testing**.
4. Click **Create new release**.

### 5.2 Upload the AAB

1. If Play App Signing is not yet enrolled, the console will prompt for enrollment — accept it.
2. Drag or browse to upload `app-release.aab`.
3. Wait for the upload and processing to complete.
4. Verify the console shows:
   - Package name: `com.yeshmishak.app`
   - Version code: `1`
   - Version name: `1.0.0`
   - No errors or warnings in the upload result

### 5.3 Add release notes

Use the prepared release notes from `release/google-play/metadata/he-IL/release-notes.txt` and `release/google-play/metadata/en-US/release-notes.txt`.

For the initial internal testing release, a simple note suffices:

> **Hebrew (he-IL):** גרסה ראשונה לבדיקות פנימיות. נא לדווח על באגים ובעיות.
>
> **English (en-US):** First internal testing release. Please report any bugs or issues.

### 5.4 Review and roll out

1. Review the release summary in Play Console.
2. Click **Save** (do not click "Review release" yet if not ready).
3. When ready, click **Review release**, then **Start rollout to Internal testing**.
4. Confirm the rollout.

## 6. Configure internal testers

### 6.1 Create a testers list

1. In Play Console, navigate to **Release** > **Testing** > **Internal testing** > **Testers** tab.
2. Click **Create email list** or use an existing list.
3. Name the list (e.g., "Yesh Mishak Core Team").
4. Add tester email addresses (Google accounts only). Each tester must have a Google account that matches the email added.

### 6.2 Recommended initial tester group

| Role | Purpose |
| :--- | :--- |
| Release owner | End-to-end verification |
| Backend developer | API integration verification |
| Frontend developer | UI/UX verification |
| QA tester | Regression testing |
| Product owner | Feature acceptance |

Internal testing supports up to 100 testers per track.

### 6.3 Share the opt-in link

After the release is rolled out:

1. Copy the internal testing opt-in link from the **Testers** tab.
2. Share the link with each tester.
3. Each tester must:
   - Open the link in a browser signed into their Google account
   - Accept the invitation to become an internal tester
   - Install the app from Google Play (it may take a few minutes to appear)

The internal testing track is not publicly visible on the Play Store.

## 7. Post-upload verification checklist

After at least one tester (the release owner) has installed the app from the internal testing track:

### 7.1 Installation verification

- [ ] App installs successfully from Google Play (not sideloaded)
- [ ] App appears in the device launcher with the correct icon (not stock Capacitor)
- [ ] App name shows correctly in the launcher
- [ ] `adb shell dumpsys package com.yeshmishak.app | findstr "versionCode versionName"` shows versionCode=1, versionName=1.0.0
- [ ] `adb shell dumpsys package com.yeshmishak.app | findstr "signatures"` shows the expected signing certificate

### 7.2 Core functionality smoke test

- [ ] App launches without crash or blank screen
- [ ] Cold start shows approved splash screen (not stock Capacitor)
- [ ] Map loads with field markers
- [ ] Google Sign-In completes successfully (uses Play app-signing certificate, not debug)
- [ ] Location permission prompt appears and works correctly
- [ ] Notification permission prompt appears and works correctly
- [ ] Field details page loads
- [ ] Game creation and joining work
- [ ] Notifications are received (push notification via FCM)
- [ ] Privacy policy link in the app opens correctly
- [ ] Terms of service link works

### 7.3 Play-specific verification

- [ ] App Links work: opening `https://yesh-mishak.com` deep links navigates to the app
- [ ] `adb shell pm get-app-links com.yeshmishak.app` shows verified status for `yesh-mishak.com`
- [ ] No Play Console pre-launch report errors (check after ~1 hour)
- [ ] Play Console shows the release as "Available to internal testers"
- [ ] Play Store listing preview shows correct icon, screenshots, and descriptions

### 7.4 Known verification blockers

If any of these fail, the failure is expected and should be documented rather than blocking the internal testing rollout:

| Item | Expected status | Action if failed |
| :--- | :--- | :--- |
| Account deletion flow | May not be implemented yet | Document as known gap; required before production release (E10-03 finding) |
| Staging vs production environment | Internal testing may use production backend | Confirm environment configuration before distributing to testers |

## 8. Tester feedback collection

### 8.1 Feedback channels

Establish a feedback channel before distributing to testers:

- **Primary:** Dedicated group chat or channel for tester bug reports
- **Secondary:** GitHub Issues with label `internal-testing`
- **Crash reports:** Sentry dashboard (configured in E09-01)

### 8.2 Feedback template

Provide testers with this template:

```
Device: [model and Android version]
Issue: [brief description]
Steps to reproduce:
1. ...
2. ...
Expected behavior: [what should happen]
Actual behavior: [what actually happened]
Screenshot/recording: [if applicable]
```

### 8.3 Monitoring

After rollout, monitor for at least 48 hours:

- [ ] Sentry dashboard: no new crash clusters
- [ ] Play Console: Android vitals show no ANR or crash spikes
- [ ] Play Console: pre-launch report reviewed
- [ ] Tester feedback reviewed and triaged
- [ ] No policy violation warnings from Play Console

## 9. Release management

### 9.1 Updating the internal testing release

To push an updated build to internal testers:

1. Increment `versionCode` in `frontend/android/app/build.gradle` (versionCode must always increase).
2. Update `versionName` if appropriate per [E10-05 version strategy](e10-05-android-version-strategy.md).
3. Rebuild the AAB following section 3.
4. Upload to the same internal testing track in Play Console.
5. Existing testers receive the update automatically (may take a few hours).

### 9.2 Halting a release

If a critical issue is found:

1. In Play Console, navigate to the internal testing release.
2. Click **Halt rollout** to stop new installations.
3. Document the issue and the halt decision.
4. Fix the issue, increment versionCode, rebuild, and create a new release.

### 9.3 Progressing to closed/open testing

Internal testing is the first step. Before progressing:

1. All post-upload verification items pass.
2. No critical or high-severity bugs remain open.
3. Crash-free rate baseline is established (see [E10-09](https://github.com/sandrusipredicts/yesh_mishak/issues/884)).
4. Play Store policy compliance review is complete (see [E10-08](https://github.com/sandrusipredicts/yesh_mishak/issues/883)).
5. Data safety form is complete (see [E10-07](https://github.com/sandrusipredicts/yesh_mishak/issues/882)).
6. Product owner approves progression.

## 10. Acceptance criteria

E10-06 is accepted when:

- [ ] This rollout guide exists in the repository and covers all steps from build to verification.
- [ ] Pre-upload validation checklist is documented.
- [ ] Post-upload verification checklist is documented.
- [ ] Tester management procedure is documented.
- [ ] Release update and halt procedures are documented.
- [ ] Progression criteria to closed/open testing are documented.
- [ ] No application code was changed.
- [ ] No Play Console actions were performed (all are documented for the release owner).

## 11. Manual Play Console actions required

The following actions must be performed by the release owner and cannot be automated from the repository:

1. **Create internal testing release** in Play Console.
2. **Upload the signed AAB** to the internal testing track.
3. **Add release notes** for the internal testing release.
4. **Roll out** the release to internal testers.
5. **Create and manage tester email list** in Play Console.
6. **Share the opt-in link** with testers.
7. **Monitor** Play Console dashboard for pre-launch reports, vitals, and policy warnings.
8. **Halt or update** the release as needed based on testing results.

## 12. Completion evidence

The release owner records the following after completing the internal testing rollout:

| Evidence item | Format |
| :--- | :--- |
| Play Console screenshot showing active internal testing release | Screenshot |
| AAB SHA-256 hash and Git commit SHA | Text |
| versionCode and versionName from `adb shell dumpsys package` | Text |
| Signing certificate fingerprint from installed build | Text |
| Tester list (email count, not addresses) | Text |
| Opt-in link shared confirmation | Text |
| Post-upload verification checklist (completed) | Markdown |
| Sentry dashboard status after 48 hours | Screenshot |
| Play Console pre-launch report status | Screenshot |
| Any known issues or exceptions documented | Markdown |

## 13. Risks and mitigations

| Risk | Mitigation |
| :--- | :--- |
| AAB rejected by Play Console | Run pre-upload validation checklist; verify targetSdk, signing, and manifest |
| Google Sign-In fails on Play-installed build | Verify Play app-signing certificate is registered in Firebase and OAuth |
| App Links do not verify | Confirm `assetlinks.json` contains Play app-signing SHA-256; check with `adb shell pm get-app-links` |
| Testers cannot find the app on Play Store | Internal testing requires opt-in link; app is not publicly listed |
| versionCode conflict | Confirm no prior upload used versionCode=1; this is the first upload |
| FCM notifications fail | Verify `google-services.json` matches the production Firebase project |
| Critical crash on first launch | Monitor Sentry; halt rollout if crash-free rate drops below 95% |

## 14. Rollback plan

Internal testing track releases can be halted at any time. No production users are affected.

1. Halt the release in Play Console.
2. Identify and fix the issue.
3. Increment versionCode (never reuse a versionCode).
4. Rebuild, re-validate, and upload a new release.
5. Resume rollout.

If the issue is with Play Console configuration rather than the app:

1. Do not upload a new AAB.
2. Fix the configuration in Play Console.
3. Resume or recreate the release.

## Related documentation

- [Android signing](android-signing.md) — E10-01
- [E10-04 store listing runbook](e10-04-google-play-store-listing-runbook.md) — E10-04
- [E10-05 version strategy](e10-05-android-version-strategy.md) — E10-05
- [Mobile build strategy](mobile-build-strategy.md) — build type definitions
- [Release checklist template](release-checklist-template.md) — general release process
- [Release versioning policy](release-versioning-policy.md) — SemVer rules
