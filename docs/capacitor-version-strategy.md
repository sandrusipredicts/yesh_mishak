# Capacitor Version Strategy

**ISSUE:** 190
**Date:** 2026-06-30
**Status:** Approved strategy reference
**Scope:** Documentation and audit only - no upgrades, no package changes, no native project changes

---

## 1. Review Summary

| Property | Value |
| :--- | :--- |
| Overall decision | **GO** - target version selected, all packages aligned |
| Target major version | **Capacitor 8.x** |
| Exact installed versions | @capacitor/core 8.4.1, @capacitor/cli 8.4.1, @capacitor/android 8.4.1, @capacitor/push-notifications 8.1.1 |
| All packages on same major | Yes (major 8) |
| Upgrades performed | No |
| Package/native files changed | No |
| Production mobile release ready | No (blocked by signing, Firebase native config, native push path, Google Sign-In, secure storage) |

---

## 2. Current Version Inventory

| Package | Range in package.json | Installed (lockfile) | Role | Assessment | Risk |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `@capacitor/core` | ^8.4.1 | 8.4.1 | Runtime - bridge between web and native | Current, aligned | None |
| `@capacitor/cli` | ^8.4.1 | 8.4.1 | Dev tooling - cap sync, cap add, cap run | Current, aligned | None |
| `@capacitor/android` | ^8.4.1 | 8.4.1 | Android platform support | Current, aligned | None |
| `@capacitor/ios` | Not installed | N/A | iOS platform support | Deferred - no iOS project yet | None now; must match major 8 when added |
| `@capacitor/push-notifications` | ^8.1.1 | 8.1.1 | Native push notification tokens (FCM/APNs) | Current, major 8 aligned | None |

All installed Capacitor packages use major version 8. No version conflicts or peer dependency warnings.

---

## 3. Target Version Decision

### 3.1 Target

| Decision | Value |
| :--- | :--- |
| Target Capacitor major | **8.x** |
| Exact current version | 8.4.1 (core, cli, android) |
| Push notifications plugin | 8.1.1 |

### 3.2 Why Capacitor 8

1. **Already installed and working.** The project has been using Capacitor 8.4.1 since the Android project was generated (PR #740).
2. **Build passes.** ISSUE-189 confirmed the Vite build output is compatible with Capacitor 8 webDir.
3. **Official plugin support.** `@capacitor/push-notifications` 8.1.1 is compatible with Capacitor 8 core.
4. **No reason to upgrade or downgrade.** No functionality requires a newer or older version.

### 3.3 Why No Upgrade in ISSUE-190

1. ISSUE-190 is a documentation and audit issue, not an implementation issue.
2. The current version works. Upgrading introduces risk without solving a current problem.
3. Any future upgrade must follow the upgrade policy (Section 5).

### 3.4 Why No Downgrade

1. Capacitor 8 is the current installed version. Downgrading would require regenerating native projects.
2. No blocker requires a downgrade. The `@codetrix-studio/capacitor-google-auth` incompatibility (requires Capacitor ^6.0.0) is solved by finding a Capacitor 8 compatible alternative, not by downgrading Capacitor.

---

## 4. Version Alignment Rules

1. **All official Capacitor packages must use the same major version.** `@capacitor/core`, `@capacitor/cli`, `@capacitor/android`, and `@capacitor/ios` (when added) must all be on major 8.
2. **Official Capacitor plugins must use the same major version.** `@capacitor/push-notifications` and any future official plugins must be on major 8.
3. **No mixed major versions.** A PR that introduces a Capacitor package on a different major version than the rest must be rejected.
4. **Future plugins must be checked before installation.** Per ISSUE-186 plugin governance policy, any new plugin must declare Capacitor 8 peer compatibility before approval.
5. **The lockfile is the source of truth for exact installed versions.** `package-lock.json` records the exact resolved version.
6. **The package.json caret ranges (^8.x.x) allow minor/patch updates within major 8.** This is acceptable as long as the lockfile pins the exact version and updates are intentional (not casual `npm update`).

---

## 5. Upgrade Policy

### 5.1 Minor/Patch Upgrades (e.g., 8.4.1 to 8.5.0)

Minor and patch upgrades within the same major version are allowed but must be intentional:

1. Create a dedicated issue or include in a planned maintenance task.
2. Review the Capacitor changelog for breaking changes (even within minor versions).
3. Upgrade all official Capacitor packages together in the same PR.
4. Run `npx cap sync` after upgrading.
5. Verify the Android build passes.
6. Verify iOS build passes (if iOS project exists).
7. Run the application in a WebView to confirm basic functionality.
8. Document the upgrade in `docs/product-decisions.md`.

### 5.2 Major Upgrades (e.g., 8.x to 9.x)

Major upgrades require a dedicated issue with full planning:

1. **Dedicated issue required.** No major upgrade during unrelated feature work.
2. **Migration guide review.** Read the official Capacitor migration guide before starting.
3. **Plugin compatibility audit.** Verify all installed plugins have versions compatible with the new major.
4. **Build validation.** Test Android and iOS builds after upgrade.
5. **Native project impact.** Review whether native project files need regeneration or migration.
6. **Rollback plan.** Document how to revert if the upgrade fails (git revert, lockfile restore).
7. **Owner approval.** Major upgrades require explicit owner approval before merging.
8. **Documentation update.** Update this document, the plugin audit, and the compatibility report.

### 5.3 Prohibited Practices

1. No casual `npm update` that silently bumps Capacitor packages.
2. No upgrading Capacitor packages as a side effect of another PR.
3. No adding a plugin that requires a different Capacitor major version.
4. No upgrading only some Capacitor packages while leaving others on the old version.

---

## 6. Downgrade Policy

1. **Downgrades are forbidden by default.**
2. A downgrade is allowed only if ALL of the following are true:
   - The current major version blocks a required feature with no workaround.
   - No maintained plugin, custom native code, or alternative approach can solve the problem on the current major.
   - The risk of downgrading (native project regeneration, plugin incompatibility, feature regression) is documented.
   - Native project impact is reviewed (Android project may need regeneration).
   - Owner explicitly approves the downgrade.
3. A downgrade must be handled in a dedicated issue, not as part of other work.
4. The downgrade issue must include a rollback plan in case the older version introduces new problems.

---

## 7. Toolchain Compatibility

### 7.1 Known Requirements

| Toolchain | Requirement | Verified From Repo | Status |
| :--- | :--- | :--- | :--- |
| Node.js | Required for Capacitor CLI | Yes (project builds) | Verified |
| npm | Required for dependency management | Yes (lockfile exists) | Verified |
| Vite | 8.0.16 - builds to `dist/` | Yes (ISSUE-189 audit) | Verified |
| React | 19.2.7 - compatible with WebView | Yes (ISSUE-189 audit) | Verified |

### 7.2 External Verification Required

The following toolchain requirements cannot be fully verified from the repository alone. They must be checked against official Capacitor 8 documentation or tested on the build machine before production builds:

| Toolchain | Requirement | Status |
| :--- | :--- | :--- |
| Android Studio | Version required by Capacitor 8 | External verification required |
| Android SDK | Minimum SDK level, target SDK level, build tools version | External verification required |
| Gradle | Version required by Capacitor 8 Android plugin | External verification required |
| JDK | Version required by Gradle and Android toolchain | External verification required |
| Xcode | Version required by Capacitor 8 iOS (when iOS project is added) | External verification required (deferred) |
| CocoaPods | Required for iOS dependencies (when iOS project is added) | External verification required (deferred) |

### 7.3 Follow-Up

A dedicated toolchain verification task should be created before the first production Android build attempt. This task should:

1. Check the local development machine against Capacitor 8 requirements.
2. Document the verified Android Studio, SDK, Gradle, and JDK versions.
3. Confirm the CI/CD environment meets the same requirements (if CI mobile builds are planned).

---

## 8. Plugin Compatibility

### 8.1 Current Plugins

| Plugin | Version | Capacitor Major | Status |
| :--- | :--- | :--- | :--- |
| `@capacitor/push-notifications` | 8.1.1 | 8 | Compatible - official Capacitor plugin |

### 8.2 Rejected Plugins

| Plugin | Reason | Status |
| :--- | :--- | :--- |
| `@codetrix-studio/capacitor-google-auth` | Requires Capacitor ^6.0.0, incompatible with Capacitor 8 | Not installed (per ISSUE-186 audit) |

### 8.3 Future Plugin Requirements

- Any future Google Sign-In plugin must support Capacitor 8.x peer dependency.
- Any future secure storage plugin must support Capacitor 8.x peer dependency.
- All plugin additions must follow the ISSUE-186 governance process, which includes Capacitor version compatibility as a required check.

---

## 9. Native Project Compatibility

### 9.1 Android

| Item | Status |
| :--- | :--- |
| Project exists | Yes (`frontend/android/`) |
| Generated under Capacitor | 8.x (PR #740) |
| `applicationId` | `com.yeshmishak.app` |
| Build type | Debug possible; release signing not configured |
| Last sync | At project generation time |

### 9.2 iOS

| Item | Status |
| :--- | :--- |
| Project exists | No |
| Generation deferred | Yes (future issue) |
| When generated | Must use Capacitor 8.x to match the rest of the project |

### 9.3 Native Project Regeneration Policy

1. Native projects must not be regenerated unless explicitly approved.
2. If a Capacitor major upgrade requires native project regeneration, this must be documented in the upgrade issue and approved by the owner.
3. `npx cap sync` is allowed during planned maintenance or upgrade tasks but not during unrelated feature work.
4. `npx cap add ios` must use the same Capacitor major version as the Android project (8.x).

---

## 10. Known Risks

| ID | Area | Severity | Finding | Impact | Follow-Up | Blocks Debug Build | Blocks Production |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| R-01 | Google Sign-In | High | No Capacitor 8 compatible Google Sign-In plugin identified | Primary login at risk in native app | Resolve OD-02 (ISSUE-181) | No (email/password fallback) | Yes |
| R-02 | Secure storage | High | No secure storage plugin selected for Capacitor 8 | JWT in localStorage not secure for production | Resolve OD-01 (ISSUE-181) | No | Yes |
| R-03 | Toolchain | Medium | Android Studio/SDK/Gradle/JDK requirements not externally verified | Production build may fail on untested machine | Dedicated toolchain verification task | No (local dev works) | Potentially |
| R-04 | iOS toolchain | Low | Xcode/CocoaPods requirements not verified (iOS deferred) | Cannot build iOS until verified | Verify when iOS project is added | No (iOS deferred) | No (iOS deferred) |
| R-05 | Signing | High | No production signing key (B-02) | Cannot sign production builds | Create signing key | No | Yes |
| R-06 | Firebase native | High | No `google-services.json` (B-03) | Native FCM will not initialize | Download from Firebase Console | No | Yes |

---

## 11. Final Decision

### 11.1 Capacitor Version Strategy

**GO.** The target Capacitor major version is 8.x. All installed packages are aligned on major 8. Version alignment rules, upgrade policy, and downgrade policy are defined. No upgrades or downgrades are performed in ISSUE-190.

### 11.2 Production Mobile Release Readiness

**NO-GO.** Production release remains blocked by previously documented blockers (signing key B-02, Firebase native config B-03, native Google Sign-In B-01, CORS B-04, secure storage OD-01). These are tracked in `docs/epic-03-completion-review.md` and `docs/mobile-application-architecture.md`.
