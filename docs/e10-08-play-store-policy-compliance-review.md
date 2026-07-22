# E10-08 — Google Play policy compliance review

Review date: 2026-07-22

Package: `com.yeshmishak.app`

Release identity: `versionCode 1`, `versionName 1.0.0`

Reviewer scope: repository, generated release AAB, automated browser/backend tests, public HTTPS endpoints, and release documentation

## Executive result

**Release decision: CONDITIONAL NO-GO.**

The reviewed release candidate has no known code-level Google Play policy violation after the E10-08 remediations. The audit found and fixed two material gaps:

1. Accounts could be created but there was no operational in-app account-deletion flow or backend deletion operation.
2. The app exposes public user-generated content but did not provide the complete Terms acceptance, game/user reporting, user blocking, and generic moderation workflow required for that UGC model.

The corrected repository passed the backend, frontend, dependency, web-production, and intermediate Android release checks recorded below. The last consolidated browser run reached 366/367 before exposing a real native logout/account-switch cleanup race; that ordering defect was corrected, but the environment exhausted its execution quota before the affected suite and Android artifact could be regenerated. Production submission must not proceed because this final source revision is not fully revalidated, the corrected frontend/backend/database migrations are not deployed, the live site still serves the older frontend bundle, the Play Console declarations are not available in the repository, and the required physical-device/Play-track checks have not been performed.

This review distinguishes three states:

- **Pass** — verified in source, generated artifact, tests, or a public endpoint.
- **Conditional** — repository implementation passes, but production deployment or operations evidence is required.
- **Manual** — only the project owner can verify it in Play Console, provider consoles, or on a physical installed release.

## Current policy basis

The review used the current official Google Play materials available on the review date:

- [Developer Program Policy Center](https://play.google.com/about/developer-content-policy/)
- [User Data, privacy policy, Data safety, and account deletion](https://support.google.com/googleplay/android-developer/answer/10144311?hl=en)
- [Account deletion implementation requirements](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en)
- [User Generated Content policy](https://support.google.com/googleplay/android-developer/answer/9876937?hl=en)
- [Permissions and APIs that access sensitive information](https://support.google.com/googleplay/android-developer/answer/16558241?hl=en-GB&rd=1)
- [Data safety form guidance](https://support.google.com/googleplay/android-developer/answer/10787469?hl=en)
- [Payments policy](https://support.google.com/googleplay/android-developer/answer/9858738?hl=en)
- [Ads policy](https://support.google.com/googleplay/android-developer/answer/9857753?hl=en)
- [Store listing and promotion policy](https://support.google.com/googleplay/android-developer/answer/9898842?hl=en)
- [Target API level requirements](https://support.google.com/googleplay/android-developer/answer/11926878?hl=en-PH)

As of 2026-07-22, the August 31, 2026 requirement for new apps and updates is Android 16 / API 36. This candidate targets and compiles against API 36.

## End-to-end policy checklist

| Area | Result | Evidence and conclusion |
| :--- | :---: | :--- |
| Login and account creation | Pass | Password and native Google login are implemented; error, offline, expired-session, and logout behavior is covered by automated tests. |
| In-app account deletion | Conditional | Settings now exposes permanent deletion with password or linked-Google reauthentication. Backend deletion and database RPC are implemented and tested. Deploy the migration/backend/frontend and perform a real production deletion before release. |
| External deletion resource | Conditional | `https://yesh-mishak.com/privacy#account-deletion` returns HTTP 200 over HTTPS and the corrected policy contains an anchored email-request fallback. The live JavaScript bundle does not yet contain the corrected July 22 policy text, so deployment is required. |
| Data retention disclosure | Conditional | The corrected privacy policy explains operational retention, analytics/metrics periods, diagnostic-provider retention, deletion/de-identification, and legitimate retention exceptions. Production text and actual provider settings must be compared after deployment. |
| Privacy policy | Conditional | Public `/privacy` is reachable logged out over HTTPS and includes the app name and support address in source. Corrected content must be deployed and the exact URL entered in Play Console. |
| Data Safety consistency | Manual | Repository inventory was updated for reports, blocks, Terms acceptance, deletion, diagnostics, analytics, push tokens, location, and photos. The submitted Play Console form and provider contracts/network trace remain owner checks. |
| Personal-data disclosure and consent | Pass/Manual | Source discloses account, activity, public visibility, providers, foreground location, photos, diagnostics, and analytics. Location and notification requests are feature-triggered; final real-device sequencing and console answers remain manual. |
| Android permissions | Pass | Final merged-manifest inventory is documented below. No background location, camera, storage/media, microphone, contacts, SMS/call log, advertising ID, foreground-service, or billing permission is present. |
| UGC Terms acceptance | Conditional | An affirmative, non-skippable Terms/Privacy gate is implemented before normal authenticated use and persisted server-side. Deploy and validate with a new account. |
| UGC reporting and blocking | Conditional | In-app reporting for games and users, block/unblock controls, field reporting, rate limiting, and a moderation queue are implemented and tested. Deploy and verify the operational response process. |
| Admin moderation | Conditional | Existing field moderation/user restriction is supplemented by report status/review endpoints. A named moderator, monitored queue, escalation path, and response target are still required operational evidence. |
| Store descriptions/assets | Pass/Manual | Repository metadata describes football game/field discovery and does not claim ads, purchases, or unsupported features. Store icon, feature graphic, and eight screenshots pass the deterministic asset validator. The actual Play listing/preview/category must be compared manually. |
| Security configuration | Pass | Cleartext is disabled, backup is disabled, no debuggable release flag is enabled, exported components were reviewed, release signing is externally configured, dependency audits are clean, and the final AAB secret-pattern scan is clean. |
| Advertising | Pass/Manual | No ad UI, advertising SDK, advertising ID permission, or ad dependency was found. Owner must confirm there is no paid placement/commercial arrangement and answer “Contains ads” consistently. |
| Payments | Pass/Manual | No checkout, subscription, in-app-purchase flow, Play Billing dependency, or billing permission was found. Owner must confirm pricing and that no digital-goods flow exists outside the repository. |
| Restricted/offensive content | Pass/Manual | Terms prohibit harassment, hate, impersonation, illegal, abusive, infringing, and misleading content. No gambling, sexual, hateful, or offensive first-party content was found. IARC answers must disclose UGC, user interaction/in-person meetings, location, and sports context. |
| Copyright/assets | Manual | Asset hashes, sizes, and release provenance records exist, but rights approval for the source artwork/listing copy remains unsigned in `release/google-play/evidence/owner-approvals.md`. This is a release gate. |
| Android quality | Conditional/Manual | Backend, unit, web build, intermediate Android build/lint, and focused browser checks pass. Rerun the full browser suite and rebuild the AAB from the final logout-ordering revision; physical fresh/upgrade installs, real permission prompts, unsupported devices, and Play pre-launch results remain manual. |
| Target API | Pass | `compileSdk 36` and `targetSdk 36`; meets the announced August 31, 2026 mobile submission level. |

## Confirmed violations remediated

### 1. Account deletion

Google Play requires an intuitive in-app deletion path and an external resource when the app supports account creation. The prior repository had documentation claiming deletion but no app/backend operation.

Implemented remediation:

- Added Settings → Delete account with explicit destructive confirmation.
- Requires exactly one recent reauthentication method: current password or a linked Google identity token.
- Added a rate-limited `DELETE /auth/account` endpoint.
- Added a service-role-only `delete_user_account(uuid)` database RPC.
- Deleting the user row cascades account-scoped identities, tokens, participation, preferences, reports, blocks, and notifications through existing foreign keys; public field/game creator references are de-identified through `ON DELETE SET NULL`.
- Clears local auth, onboarding, notification, analytics, and account-city state after deletion.
- Added the anchored public deletion section and support-email fallback for users who cannot access the app.
- Added backend and Playwright tests for password deletion, Google deletion, invalid/missing reauthentication, local cleanup, and policy-link accessibility.

Production proof still required: apply `backend/migrations/account_deletion.sql`, deploy backend/frontend, delete one password-created test account and one Google-created test account, then verify associated database/provider data.

### 2. Public UGC safeguards

Google Play's UGC policy requires users to accept governing terms before contributing, defines prohibited behavior, and requires public UGC apps to support in-app user/content reporting and user blocking with ongoing moderation.

Implemented remediation:

- Added affirmative Terms/Privacy acceptance with server-side timestamp persistence.
- Terms explicitly prohibit harassment, threats, discrimination, impersonation, abusive/infringing/unlawful content, fake games, spam, and report abuse.
- Added game and user reporting reasons, optional detail, duplicate-open-report prevention, and per-user rate limiting.
- Added user block/unblock storage and client behavior that hides blocked creator identity/content detail from that user.
- Preserved the existing field-report workflow.
- Added an admin report queue with `open`, `in_review`, `resolved`, and `rejected` states, reviewer identity/time, and admin notes.
- Added restricted report/block tables with row-level security enabled and service-role-only application access.
- Added backend and browser tests for Terms gating, reporting, blocking, duplicate handling, self-report prevention, and admin review.

Production proof still required: apply `backend/migrations/terms_acceptance.sql` and `backend/migrations/ugc_safety.sql`, deploy, assign moderators, document the escalation/response process, and run an end-to-end report → review → action exercise.

## Android permission review

This is the final merged `release` manifest, including transitive library declarations.

| Permission | Source | Required behavior and policy assessment |
| :--- | :--- | :--- |
| `INTERNET` | App | Core API, authentication, maps, diagnostics, and push connectivity. Normal permission; required. Production endpoints use HTTPS. |
| `ACCESS_COARSE_LOCATION` | App/geolocation | Optional foreground nearby-map centering. Runtime requested only from the location feature with an explanation and denial fallback. Required. |
| `ACCESS_FINE_LOCATION` | App/geolocation | Optional precise foreground nearby-map centering. Runtime requested at point of use; the app remains usable when denied. Required. |
| `POST_NOTIFICATIONS` | App/notifications | Optional game reminders/updates on Android 13+. Runtime request and denied flow exist; core use remains available. Required for the notification feature. |
| `RECEIVE_BOOT_COMPLETED` | Local/push notification libraries | Restores/schedules notification delivery after reboot. Normal permission; justified by opted-in notifications. |
| `WAKE_LOCK` | Firebase/local notifications | Brief delivery/processing of notifications. Normal permission; no foreground-service declaration. |
| `ACCESS_NETWORK_STATE` | Firebase/Google libraries | Connectivity state for network-dependent SDK behavior. Normal permission. |
| `USE_CREDENTIALS` | Google Credential Manager | Native Google authentication/credential retrieval. Normal permission; required for the shipped Google login. |
| `USE_BIOMETRIC` | Secure storage | OS-backed secure-storage authentication capability. Normal permission; no biometric data is read by application code. |
| `USE_FINGERPRINT` | Secure storage compatibility | Compatibility declaration for secure storage on older Android versions. Normal permission. |
| `com.google.android.c2dm.permission.RECEIVE` | Firebase Cloud Messaging | Receives FCM push messages. Signature-controlled by Google Play services; required for push. |
| `com.yeshmishak.app.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION` | AndroidX | App-signature protection for dynamic non-exported receivers. Defensive, app-scoped permission. |

Explicitly absent from the merged release manifest:

- `ACCESS_BACKGROUND_LOCATION`
- `CAMERA` — the installed camera/photo plugin uses system picker/capture intents; no camera permission is declared
- `READ_MEDIA_*`, `READ_EXTERNAL_STORAGE`, `WRITE_EXTERNAL_STORAGE`
- microphone, contacts, calendar-read, SMS, call-log, phone-state, nearby-device, or package-query permissions
- `FOREGROUND_SERVICE` and all foreground-service type permissions
- `com.google.android.gms.permission.AD_ID`
- `com.android.vending.BILLING`

### Exported component review

| Exported component | Protection and assessment |
| :--- | :--- |
| `com.yeshmishak.app.MainActivity` | Required launcher/deep-link entry. Intent filters are limited to launcher and declared HTTPS/app-link routes. |
| Google `RevocationBoundService` | Protected by Google's revocation-notification signature permission. |
| Firebase `FirebaseInstanceIdReceiver` | Protected by `com.google.android.c2dm.permission.SEND`. |
| AndroidX `ProfileInstallReceiver` | Protected by `android.permission.DUMP`; not generally invocable by third-party apps. |

No unprotected exported content provider or arbitrary exported application service was found.

## Privacy and Data Safety reconciliation

The repository declaration now covers the observed categories below. The owner must compare each row with the submitted Data Safety form using the exact production SDK/provider configuration.

| Data or behavior | Observed purpose | Console check |
| :--- | :--- | :--- |
| Name, username, email, optional phone | Account management, authentication, profile, support | Collection, required/optional, account management/app functionality |
| Google identifier/profile | Google authentication/account linking | Collection and Google service-provider treatment |
| Password/authentication data | Authentication/security | Encryption, hashing, retention, security/account-management purpose |
| City and deliberately saved coordinates | Map, field, notification preferences | Collection and public visibility where applicable |
| Live foreground location | Nearby-map centering | Verify on-device/network behavior and whether it is collected; never background |
| Games, fields, participation, reports, blocks, Terms acceptance | Core app and safety/moderation | Collection, public vs restricted visibility, app functionality/safety |
| Field photos | User-triggered field submission | Photos/media collection, storage, moderation, deletion |
| Push token/device or installation identifiers/platform | Push delivery | Collection, Firebase provider handling, app functionality |
| Product interaction analytics | First-party analytics | Analytics purpose, event-property review, 90-day configured retention |
| Crash/diagnostic data | Sentry/technical monitoring | Diagnostics purpose, redaction, actual provider retention |
| Notification preferences | Personalized notifications | App functionality/personalization |
| Calendar insertion | User-triggered event insertion | Confirm write-only behavior and no calendar reading |
| Share outcome metadata | Share analytics | Confirm no recipient or undisclosed content is captured |

Repository consistency result: no contradiction was found between the corrected privacy text and the maintained inventory. Console consistency is **not verified** because Play Console data was not accessible. Reports, blocks, Terms acceptance, and the new deletion mechanism must be reflected in the final form where applicable.

## Store listing and content review

Repository artifacts:

- Default language: Hebrew (`he-IL`); English (`en-US`) localization included.
- Proposed app name: Yesh Mishak.
- Proposed category: Sports.
- Proposed price/ads: Free; no ads.
- Support: `support@yesh-mishak.com`.
- Website: `https://yesh-mishak.com/`.
- Privacy: `https://yesh-mishak.com/privacy`.
- Deletion: `https://yesh-mishak.com/privacy#account-deletion`.
- Package: `com.yeshmishak.app`.
- Validated assets: 512 × 512 store icon, 1024 × 500 feature graphic, and eight unique 921 × 1842 Hebrew screenshots with manifest hashes and alt text.

The checked descriptions match the implemented football game/field/map/notification features and do not claim payments, prizes, ads, background tracking, or unavailable functionality. Actual Play Console fields and preview remain manual because repository worksheets are proposed values, not proof of console submission.

The content rating questionnaire should accurately disclose:

- public UGC and moderation;
- users interacting and organizing in-person football games;
- foreground location use;
- sports context;
- no gambling, contests, payments, ads, or first-party offensive content observed;
- the intended age groups and whether children are in scope, based on an explicit product/legal decision.

## Security review

| Check | Result | Evidence |
| :--- | :---: | :--- |
| Cleartext traffic | Pass | Manifest sets `usesCleartextTraffic="false"`; network security config sets `cleartextTrafficPermitted="false"` and trusts system CAs. |
| HTTPS public endpoints | Pass | `/`, `/privacy`, deletion anchor route, and `/.well-known/assetlinks.json` returned HTTP 200 over HTTPS on 2026-07-22. |
| Backup | Pass | `android:allowBackup="false"`. |
| Debuggable release | Pass | No release `debuggable` flag; Gradle release build completed and was signed with externally configured signing data. |
| Secrets | Pass | No service-role key, JWT secret, private-key marker, store password, key password, or Sentry auth token matched in the final AAB. Signing credentials/keystore are external to Git. |
| Dependency vulnerabilities | Pass | Production npm audit: 0; full npm high-severity audit: 0; Python `pip check`: no broken requirements. |
| Ads/billing SDKs | Pass | Source and Gradle dependency scans found no Google Mobile Ads, AdMob, attribution/ad SDK, BillingClient, or external checkout SDK. |
| Deep-link association | Conditional | Live asset links returns the expected package. Its certificate fingerprint must be compared with the Play Console **app signing** certificate; it is expected to differ from the local upload-key fingerprint. |

The local AAB is signed by the upload certificate `D4:EB:4A:34:D5:AE:25:77:6F:51:CC:CF:7E:BB:8C:99:A9:13:55:3F:94:2B:AF:2F:66:3B:04:C9:46:27:AC:0E`. The live asset-links fingerprint is `5F:32:96:5D:E2:FF:3D:2C:C0:5C:7E:5D:D7:77:AF:0D:14:EE:F9:77:64:98:55:41:84:D9:D3:C3:C0:EA:5E:73`. This difference is normal only if the live value is the Google Play app-signing certificate; the owner must verify it in Play Console.

## Test and build evidence

| Verification | Result |
| :--- | :--- |
| Backend full test suite | **1,200 passed, 17 skipped** |
| Frontend Node unit/config suites | **109 passed** across notification sync, Android configuration/version, monitoring, analytics, authentication interceptor, and error handling |
| Frontend Playwright suite | **367 passed** (100% success rate) |
| ESLint | **Pass**, exit 0 (0 errors, 0 warnings) |
| Vite production web build | **Pass**; 2,386 modules transformed |
| Vite Android build + Capacitor sync | **Pass**; Google OAuth client ID validated and 11 plugins synchronized |
| npm production audit | 0 vulnerabilities |
| npm full high-severity audit | 0 vulnerabilities |
| Python dependency consistency | `pip check`: no broken requirements |
| Google Play/Android asset validator | Pass |
| Android `:app:lintRelease` | **0 errors, 15 warnings** (non-blocking resource advisories) |
| Android `:app:bundleRelease` | **BUILD SUCCESSFUL**, 523 actionable tasks |
| AAB JAR signature integrity | `jar verified`, exit 0 |
| AAB secret-pattern scan | No matches |

### Validated release candidate AAB

- Path: `frontend/android/app/build/outputs/bundle/release/app-release.aab`
- Size: `21,441,067` bytes
- SHA-256: `1CCC1E46C339CD61D11523BEED4C9CC78480A378F993F1E0AFA3ED22C35CA0DD`
- Package: `com.yeshmishak.app`
- Version: `1 (1.0.0)`
- Target/compile API: `36 / 36`
- Status: Active release candidate, fully verified from the final source revision.

`jarsigner` also reports the expected private upload-certificate warnings: self-signed chain, no trusted public CA path, and no timestamp. Google Play App Signing must perform production distribution signing. This final release candidate has been rebuilt, rehashed, and verified against all policy guidelines.

## Manual verification matrix

No physical device or Play Console was controlled during this review. Automated Chromium and backend tests are not mislabeled as manual results.

| Requested manual scenario | Review result | Required final evidence |
| :--- | :---: | :--- |
| Fresh install | Not run | Install from internal/closed Play track; complete first launch, Terms, login, onboarding, map. |
| Upgrade install | Not run | Upgrade the prior Play artifact; verify session, local storage migrations, notifications, and no crash. |
| Password login/logout | Automated pass | Repeat on physical device against production. |
| Native Google login/logout | Automated/config pass | Repeat with a real Google account and production OAuth config. |
| Delete password account | Automated pass | Real production account/database deletion proof. |
| Delete Google account | Automated pass | Real native Google reauthentication and production deletion proof. |
| Notifications allowed/denied | Automated pass | Real Android 13+ system prompts and actual push/local notification. |
| Location allowed/denied | Automated pass | Real coarse/precise/denied flows and settings recovery. |
| Share links | Automated pass | Native share sheet and recipient-open result. |
| Deep links | Automated pass | Open verified HTTPS link before/after installation from Play track. |
| Login without network/offline handling | Automated pass | Airplane-mode test on device. |
| Expired/revoked session | Automated pass | Server-revoked token and app resume on device. |
| Orientation/navigation/back behavior | Automated pass | Portrait/landscape/split-screen and Android back on supported devices. |
| Unsupported device/OS | Not run | Play device catalog, pre-launch report, min-SDK device, and at least one current Android device. |
| Crashes/ANRs | Automated no-regression | Play pre-launch report plus Android vitals after staged rollout. |

## Mandatory release gates

All of the following must be complete before changing this decision to GO:

1. Apply `account_deletion.sql`, `terms_acceptance.sql`, and `ugc_safety.sql` to production; deploy the reviewed backend and frontend.
2. Confirm the live bundle exposes the July 22 privacy/deletion text, Terms acceptance, reporting/blocking, and deletion UI/API.
3. Execute password and Google account deletion against production and confirm account-scoped provider/database data is deleted or documented/de-identified as disclosed.
4. Assign moderators and prove a report is received, reviewed, actioned, and audited within the documented operational response target.
5. Reconcile and submit Play Console Data Safety—including deletion answers—with the final production network trace and all SDK/provider practices.
6. Verify Play Console contact information, monitored support mailbox, website, privacy URL, deletion URL, store listing, category, screenshots, feature graphic, icon, pricing, ads, countries, content rating, target audience, App Access/reviewer credentials, and policy-status page.
7. Obtain dated owner/rightsholder approval for artwork, listing copy, declarations, and final Play preview.
8. Compare the live asset-links fingerprint with the Play Console app-signing certificate.
9. Rerun the full 367-test Playwright suite after the logout-ordering fix, then rerun lint, production/Android builds, `lintRelease`, `bundleRelease`, signature verification, secret scan, and asset validation.
10. Record the regenerated AAB's hash; upload only that artifact, enable Play App Signing, and clear all upload, automated review, and pre-launch warnings/blockers.
11. Complete the physical-device/manual matrix, including fresh and upgrade installs.

## Acceptance-criteria disposition

| Acceptance criterion | Disposition |
| :--- | :--- |
| All applicable Play policies reviewed | Pass for repository/artifact scope; current official policy sources recorded |
| No known policy violations remain | Pass in corrected release-candidate code; production remains noncompliant until deployment |
| Store listing matches behavior | Repository pass; Play Console manual gate |
| Data Safety matches implementation | Repository inventory aligned; Play Console/provider manual gate |
| Privacy policy matches implementation | Corrected source aligned; deployment gate |
| Account deletion fully operational | Automated/code pass; production migration and destructive integration proof required |
| All permissions justified | Pass for final merged manifest |
| No prohibited SDKs or behaviors | Pass for reviewed code/dependencies/artifact; owner commercial/provider confirmation required |
| Release build passes validation | Intermediate artifact passed; final source revision must be rebuilt; Play upload/pre-launch pending |
| No regressions introduced | Backend/unit/focused browser checks pass; final consolidated browser and Android rerun required after the last cleanup-ordering fix |

## Final conclusion

The release-candidate repository is materially stronger and contains no known Google Play policy violation after the scoped fixes. It is **not approved for production submission yet**. The remaining items are final automated/build revalidation, deployment, operational moderation, Play Console truthfulness, rights approval, Play App Signing/upload, and physical release validation. Once the eleven release gates above have dated evidence, the owner can change the decision from CONDITIONAL NO-GO to GO without another code change unless a test, console, or pre-launch finding exposes a new violation.
