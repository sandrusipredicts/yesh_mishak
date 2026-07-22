# E10-08 release-candidate build verification

Date: 2026-07-22

Full report: `docs/e10-08-play-store-policy-compliance-review.md`

| Check | Result | Notes |
| :--- | :--- | :--- |
| Backend full suite | Pass | 1,200 passed, 17 skipped. |
| Frontend Node suites | Pass | 109 tests passed across notification, Android configuration/version, monitoring, analytics, authentication interceptor, and error handling. |
| Full Playwright suite | Pass | 367 passed. |
| `npm run lint` | Pass | ESLint exit 0. |
| `npm run build` | Pass | Vite production build completed. |
| `npm run build:android` | Pass | Google OAuth client ID validation and Android-mode Vite build passed. |
| Capacitor sync | Pass | Eleven configured plugins synchronized. |
| npm audits | Pass | Production audit: 0 vulnerabilities; full high-severity audit: 0 vulnerabilities. |
| Python dependency consistency | Pass | `pip check` found no broken requirements. |
| Google Play/Android asset validator | Pass | Store graphics, eight screenshots, metadata lengths, manifest hashes, launcher, and splash resources passed. |
| Android `:app:lintRelease` | Pass | 0 errors, 15 resource/icon/splash warnings. |
| Android `:app:bundleRelease` | Pass | Gradle BUILD SUCCESSFUL; 568 tasks; package `com.yeshmishak.app`, version `1 (1.0.0)`. |
| AAB signature | Pass | `jarsigner`: `jar verified`, exit 0. |
| AAB secret scan | Pass | No service-role/JWT/private-key/signing-password/Sentry-auth-token pattern matched in the final artifact. |
| Installed-device/manual matrix | Pending owner | Fresh/upgrade install, native prompts, real push/location/share/deep-link, production deletion, unsupported device, and pre-launch checks remain required. |
| Play Console upload/pre-launch | Pending owner | Upload the recorded AAB, verify Play App Signing/asset links, and clear console findings before production. |

## Generated release candidate artifact

- `frontend/android/app/build/outputs/bundle/release/app-release.aab`
- Size: `21,441,067` bytes
- SHA-256: `1CCC1E46C339CD61D11523BEED4C9CC78480A378F993F1E0AFA3ED22C35CA0DD`
- `compileSdk 36`, `targetSdk 36`

The release remains a conditional no-go until final deployment, Play Console, rights approval, moderation-operations, production account-deletion, and physical-device gates in the full E10-08 report are complete.
