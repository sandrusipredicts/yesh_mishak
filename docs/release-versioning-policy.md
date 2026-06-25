# Release Versioning Policy

## 1. Purpose

This document defines the official release versioning policy for the yesh_mishak project. It is the source of truth for how release version numbers are assigned, incremented, and communicated.

A consistent versioning policy ensures that all team members follow the same format, that releases are traceable and predictable, and that the project is prepared for App Store and Google Play distribution where strict version and build number rules apply.

## 2. Policy Summary

The project uses **Semantic Versioning (SemVer)** format:

```
MAJOR.MINOR.PATCH
```

Examples:
- `1.0.0` — initial stable production release
- `1.1.0` — new feature added
- `1.1.1` — bug fix or hotfix

The recommended initial production/mobile release baseline is **1.0.0**.

## 3. Version Format

| Component | Meaning | When It Changes |
| :--- | :--- | :--- |
| **MAJOR** | Breaking or incompatible changes | Incremented when changes require users, admins, or deployers to change their behavior significantly |
| **MINOR** | New backwards-compatible functionality | Incremented when new features are added without breaking existing behavior |
| **PATCH** | Bug fixes and small improvements | Incremented for fixes that do not add new features or break compatibility |

Examples:
- `1.0.0` — initial stable release
- `1.1.0` — new feature release (e.g. add scheduled games)
- `1.1.1` — bugfix/hotfix release (e.g. fix game join error)
- `2.0.0` — breaking product/API behavior change (e.g. new auth model requiring re-login)

## 4. Increment Rules

### MAJOR (X.0.0)
Increment MAJOR when making changes that are incompatible with the previous version:
- Breaking API changes (removed endpoints, changed response shapes)
- Major auth/session model changes requiring users to re-authenticate
- Major database model changes requiring incompatible migration
- Major mobile app flow rewrite
- Removal of existing API fields or endpoints
- Any change requiring users, admins, or deployers to change behavior significantly

### MINOR (x.Y.0)
Increment MINOR when adding new backwards-compatible functionality:
- New features (screens, admin tools, notification features)
- New supported sports or game types
- Non-breaking API additions (new endpoints, new optional fields)
- Backwards-compatible database schema changes
- New integrations that do not affect existing behavior

### PATCH (x.y.Z)
Increment PATCH for backwards-compatible bug fixes and small improvements:
- Bug fixes
- Security fixes that do not introduce breaking behavior
- UI/UX fixes
- Performance improvements
- Documentation corrections included in a release
- Hotfixes for production issues

## 5. Pre-Release Versions

Optional pre-release labels may be appended with a hyphen:

| Label | Meaning | Example |
| :--- | :--- | :--- |
| `alpha` | Early internal testing, unstable | `1.2.0-alpha.1` |
| `beta` | Wider test group, feature-complete but may have bugs | `1.2.0-beta.1` |
| `rc` | Release candidate, final validation before production | `1.2.0-rc.1` |

Rules:
- Pre-release versions have lower precedence than the associated release (`1.2.0-alpha.1` < `1.2.0`).
- Production releases should use clean versions (e.g. `1.2.0`) without pre-release labels.
- Pre-release labels are appropriate for TestFlight, Firebase App Distribution, or internal test builds.
- Increment the numeric suffix for successive pre-release builds: `1.2.0-beta.1`, `1.2.0-beta.2`.

## 6. Build Metadata / Mobile Build Numbers

There is a distinction between the user-facing version and the internal build number:

| Concept | Format | Purpose | Example |
| :--- | :--- | :--- | :--- |
| **User-facing version** | `MAJOR.MINOR.PATCH` | Shown to users in app stores and release notes | `1.2.0` |
| **Internal build number** | Monotonically increasing integer | Required by app stores to distinguish uploads | `42` |

### App Store (iOS)
- **CFBundleShortVersionString**: User-facing version (e.g. `1.2.0`).
- **CFBundleVersion**: Build number (e.g. `42`). Must increase with every upload.

### Google Play (Android)
- **versionName**: User-facing version string (e.g. `1.2.0`). Should follow SemVer.
- **versionCode**: Integer build number (e.g. `42`). Must strictly increase with every APK/AAB upload.

### Rules
- The build number must always increase, even for the same user-facing version.
- Never reuse a build number that has been uploaded to a store.
- Multiple builds of the same version (e.g. `1.2.0` build 41, build 42) are common during testing.
- Build metadata can optionally be appended with `+` (e.g. `1.2.0+42`) but is ignored for version precedence.

## 7. Repository Version Sources

### Current State
| Source | Location | Current Value | Notes |
| :--- | :--- | :--- | :--- |
| Frontend | `frontend/package.json` → `"version"` | `0.0.0` | Default Vite scaffold value, not actively maintained |
| Backend | No version file found | N/A | No `__version__`, no `pyproject.toml` version field |
| Mobile | No mobile project exists | N/A | Not yet applicable |
| Git tags | None | N/A | No release tags exist |
| CHANGELOG | None | N/A | No CHANGELOG.md exists |

### Known Gap
There is no single source of truth for the application version. The frontend `package.json` version is the scaffold default (`0.0.0`) and is not actively maintained as a release version.

### Recommended Future Source of Truth
Define a single version source (e.g. a `VERSION` file in the repository root, or `frontend/package.json` if the project is frontend-primary). All other version references should derive from this source. This is a follow-up task.

## 8. Release Branch / Git Tag Rules

### Branch Naming
| Branch Type | Format | Example |
| :--- | :--- | :--- |
| Release branch | `release/vX.Y.Z` | `release/v1.2.0` |
| Hotfix branch | `hotfix/vX.Y.Z` | `hotfix/v1.2.1` |

### Tag Naming
| Tag Format | Example |
| :--- | :--- |
| `vX.Y.Z` | `v1.2.0` |
| `vX.Y.Z-pre.N` | `v1.2.0-rc.1` |

### Rules
- Do not tag releases before validation passes (tests, build, smoke tests).
- Do not reuse tags. If a tag was created in error, delete it and create a new one with the corrected version.
- Tag only after final approval and successful deployment.
- Tags should be annotated (`git tag -a v1.2.0 -m "Release v1.2.0"`).

## 9. Changelog Rules

Release notes should follow the [Keep a Changelog](https://keepachangelog.com/) convention with these categories:

| Category | When to Use |
| :--- | :--- |
| **Added** | New features or capabilities |
| **Changed** | Changes to existing functionality |
| **Fixed** | Bug fixes |
| **Security** | Security-related fixes or improvements |
| **Deprecated** | Features marked for future removal |
| **Removed** | Features or APIs that have been removed |
| **Known Issues** | Known problems in this release |

### Current State
No `CHANGELOG.md` exists in the repository. Creating one is a recommended follow-up.

### Recommended Format
```markdown
# Changelog

## [1.1.0] - 2026-07-15
### Added
- Scheduled games feature
### Fixed
- Game join participant count bug
```

## 10. Release Decision Rules

| Step | Responsible Party |
| :--- | :--- |
| Propose version bump type | Product owner or technical lead |
| Confirm bump type matches changes | PR reviewer |
| Approve security patch releases | Technical lead (expedited review) |
| Approve breaking (MAJOR) changes | Product owner + technical lead discussion |
| Approve App Store / Google Play release | Product owner (explicit approval required) |

Rules:
- Every release must have a clearly identified version before merging to the release branch.
- Security fixes may require an expedited patch release process.
- Breaking changes require explicit discussion before committing to a MAJOR bump.
- App Store / Google Play submissions require explicit product owner approval.

## 11. Versioning Examples for yesh_mishak

| Change | Version Bump | Example |
| :--- | :--- | :--- |
| Add scheduled games feature | MINOR | `1.0.0` → `1.1.0` |
| Fix game join bug | PATCH | `1.1.0` → `1.1.1` |
| Fix Google auth account-takeover vulnerability (no breaking change) | PATCH | `1.1.1` → `1.1.2` |
| Change auth model requiring all users to re-login | MAJOR | `1.1.2` → `2.0.0` |
| Add staging environment docs only (no app change) | No version bump | — |
| Add new sport type (basketball courts) | MINOR | `1.2.0` → `1.3.0` |
| Change database schema backwards-compatibly | MINOR or PATCH | Depends on user-visible impact |
| Remove existing API endpoint | MAJOR | `1.3.0` → `2.0.0` |
| Fix UI layout on field detail page | PATCH | `2.0.0` → `2.0.1` |
| Add admin report management dashboard | MINOR | `2.0.1` → `2.1.0` |

## 12. App Store / Google Play Readiness

| Requirement | Policy |
| :--- | :--- |
| User-facing version | Stable, understandable SemVer (e.g. `1.2.0`) |
| Internal build number | Monotonically increasing integer, never reused |
| TestFlight / internal testing | May use pre-release versions (e.g. `1.2.0-beta.1`) |
| Production store release | Clean version only (e.g. `1.2.0`), no pre-release labels |
| Release notes | Must match the version and describe user-facing changes |
| Review submission | Requires product owner approval before submission |

### Current State
No mobile app project (iOS/Android) exists in the repository. App Store and Google Play configuration will be addressed when the mobile project is created. The versioning policy is designed to be compatible with store requirements from the start.

## 13. Version Bump Checklist

Before each release:

- [ ] Identify all changes since the previous release.
- [ ] Decide MAJOR, MINOR, or PATCH based on the increment rules above.
- [ ] Check for breaking API or behavior changes (→ MAJOR).
- [ ] Check for security fixes (→ PATCH, expedited if critical).
- [ ] Update the version source of truth (once established).
- [ ] Update CHANGELOG.md or release notes (once established).
- [ ] Run all required tests and builds.
- [ ] Confirm staging validation passes (smoke test checklist).
- [ ] Confirm deployment readiness.
- [ ] Get PR review and approval.
- [ ] Create release branch and/or tag only after approval.
- [ ] For app store releases: get explicit product owner approval.

## 14. Known Gaps / Needs Confirmation

| Gap | Status |
| :--- | :--- |
| No CHANGELOG.md exists | Not implemented |
| No single app-wide version source of truth | Not implemented (`frontend/package.json` is scaffold default `0.0.0`) |
| No mobile app project (iOS/Android) | Not applicable yet |
| No automated release tagging in CI | Not implemented |
| No build number automation | Not implemented |
| No release approval checklist or workflow | Not implemented (this policy serves as the initial reference) |
| No GitHub Releases configured | Not implemented |

## 15. Recommended Follow-Up Issues

1. **Create CHANGELOG.md**: Initialize a changelog following the Keep a Changelog format.
2. **Define single source of truth for app version**: Choose a canonical version location and update `frontend/package.json` from `0.0.0` to the actual current version.
3. **Add release checklist document**: Formalize the release process with a step-by-step checklist.
4. **Add mobile build number policy**: When the mobile project is created, document build number management for iOS and Android.
5. **Add automated version validation in CI**: Add a CI step that verifies the version was bumped appropriately.
6. **Add GitHub release/tagging process**: Define how and when GitHub Releases are created from tags.

## 16. Final Result

| Item | Status |
| :--- | :--- |
| Versioning policy exists | YES |
| Format defined (MAJOR.MINOR.PATCH) | YES |
| MAJOR/MINOR/PATCH rules defined | YES |
| Pre-release version rules defined | YES |
| Build metadata / mobile build number rules defined | YES |
| App Store / Google Play considerations documented | YES |
| Team workflow documented | YES |
| Runtime behavior changed | NO |
| DB schema changed | NO |
