# iOS Code Signing Strategy

**Issue:** ISSUE-209
**Status:** Approved strategy; implementation not started
**Date:** 2026-07-01
**Approved Bundle Identifier:** `com.yeshmishak.app`

## 1. Purpose and Scope

This document defines who owns iOS signing, how development and distribution signing will be separated, where future credentials may live, and which approvals are required before physical-device, TestFlight, or App Store work begins.

This is a documentation decision only. It does not configure an Apple Developer account, change Xcode signing settings, create certificates or provisioning profiles, create App Store Connect records, or add CI secrets.

### 1.1 Current State

| Capability | Current state |
| --- | --- |
| iOS Simulator development | Available on a Mac with Xcode; no Apple signing account is required |
| GitHub Actions Xcode validation | Passing, deliberately unsigned with `CODE_SIGNING_ALLOWED=NO` |
| Physical iPhone deployment | Not configured; future work |
| Apple Developer Program membership | No organization account or Team ID is documented in this repository |
| Development certificates/profiles | None committed or documented as provisioned |
| TestFlight | Not configured; future work |
| App Store Connect app record | Not documented as created |
| Production signing | Not configured; future work |
| Signing secrets in Git | None; prohibited |

The generated Xcode project contains Capacitor's default `CODE_SIGN_STYLE = Automatic`, but no `DEVELOPMENT_TEAM` is committed. This does not mean signing is configured. The current CI workflow explicitly disables signing and must remain unsigned until a dedicated implementation issue approves a signed workflow.

## 2. Ownership Roles

Signing responsibilities are assigned to roles so the policy remains stable when personnel change. A future Apple-account setup issue must record the named people holding each role in the organization's private access register or password manager, not in this public repository.

| Role | Responsibility | Minimum staffing |
| --- | --- | --- |
| Apple Account Holder | Owns the organization membership, accepts agreements, renews membership, and authorizes Admin access | One named person |
| Apple Admin | Backup account administration; manages authorized users and signing resources under change control | Two named people, independent of the Account Holder where practical |
| iOS Maintainer | Performs local development signing and validates physical-device builds | One or more authorized developers |
| Release Manager | Selects release candidates, initiates TestFlight uploads, and coordinates App Store submission | One primary and one backup |
| Security/DevOps Owner | Manages CI environments, secret storage, audit access, rotation, and incident response | One primary and one backup |
| Product Release Approver | Gives business approval for production submission after technical gates pass | One named product owner or delegate |

**Current assignment status:** all Apple-specific roles are unassigned because no organization Apple Developer Program account is documented. Physical-device and distribution signing remain blocked until a future issue names the holders and records evidence of the account and access model.

## 3. Development Signing

### 3.1 Simulator

Any repository contributor with a supported Mac and Xcode may build and run the app in an iOS Simulator. Simulator work:

- does not require an Apple Developer Program membership, certificate, provisioning profile, Team ID, or signing secret;
- may use the committed `com.yeshmishak.app` configuration because no signed installation is produced;
- does not prove physical-device, TestFlight, or App Store readiness.

The near-term CI target may add simulator compile or runtime validation, but it must remain unsigned.

### 3.2 Physical iPhone

Physical-device installation is restricted to authorized iOS Maintainers and is future work. Before testing the official app identity on a physical device:

1. the organization must enroll in the Apple Developer Program;
2. the Account Holder/Admin must register `com.yeshmishak.app` to the organization team;
3. the developer must use their own Apple ID invited to that organization team;
4. the device must be registered or otherwise authorized by Apple's supported development-signing flow;
5. the resulting signing assets must stay in the developer's macOS Keychain/Xcode-managed storage.

Developers must not share an Apple ID, password, private key, or local Keychain. Personal teams may be used only for private experiments with a temporary, non-product Bundle Identifier. They must not claim or represent the official `com.yeshmishak.app` identity and must never be used for TestFlight or production.

### 3.3 Automatic Versus Manual Signing

- **Allowed locally:** Xcode automatic signing is allowed for authorized physical-device development after the organization team exists. Each developer selects the organization Team locally using their own Apple ID.
- **Not committed:** Team selections, personal account data, device lists, Xcode user data, and machine-specific provisioning choices must not be committed.
- **Not allowed for distribution CI by default:** TestFlight and production CI must use an explicitly reviewed, reproducible signing setup. Interactive Apple ID login or `-allowProvisioningUpdates` is not the default CI strategy.
- **Manual changes require a future issue:** Any committed `DEVELOPMENT_TEAM`, provisioning-profile specifier, signing identity, or entitlement change requires a separate reviewed implementation issue.

## 4. TestFlight Signing

TestFlight requires future organization-owned Apple setup. No TestFlight work may start until the following prerequisites are complete:

- active organization Apple Developer Program membership;
- App ID for `com.yeshmishak.app`;
- organization-owned App Store Connect app record;
- an authorized distribution certificate and App Store distribution provisioning profile, or a separately approved Apple-supported managed-signing equivalent;
- named Apple Account Holder, Admins, Release Manager, and Security/DevOps Owner;
- approved CI secret design and recovery test.

### 4.1 Ownership and Upload Responsibility

- The App Store Connect app record belongs to the organization, never to a contractor's or developer's personal account.
- The Release Manager is accountable for selecting and uploading a TestFlight build.
- An authorized iOS Maintainer or protected CI workflow may perform the technical upload.
- Upload permission must use the least-privileged Apple role that supports the required operation.
- App Store Connect API-key authentication is preferred for automation over a shared Apple password or app-specific password.

### 4.2 Distribution Certificate Strategy

- Distribution certificates and private keys are organization assets.
- The Security/DevOps Owner creates or imports CI signing material with an Apple Admin under a recorded change.
- A distribution private key must be exportable only when required for controlled backup or CI installation.
- The certificate/profile pair used by CI must be identifiable by purpose, owner, creation date, and expiry in the private credential inventory.
- TestFlight uses the protected `ios-testflight` CI environment and cannot access production-only approvals or unrelated secrets.

### 4.3 Future CI

GitHub Actions is the preferred first implementation because unsigned Xcode validation already runs there. Codemagic or Bitrise may be considered only through a separate vendor/security decision.

A future signed TestFlight workflow must:

1. run only from an explicitly allowed branch, tag, or manual dispatch;
2. use the protected `ios-testflight` GitHub Environment;
3. require Release Manager approval;
4. install credentials into a temporary keychain on an ephemeral macOS runner;
5. remove the temporary keychain and provisioning profile in an `always()` cleanup step;
6. archive and export the `.ipa` without exposing signing values in logs;
7. upload with a least-privileged App Store Connect API key;
8. retain non-secret build metadata and audit evidence.

## 5. Production Signing

Production signing is a separate release operation, even when Apple permits reuse of an organization distribution certificate.

- Production uses the final Bundle Identifier `com.yeshmishak.app`.
- Production release credentials are organization-owned and available only through the protected `ios-production` CI environment or an equivalent approved release system.
- Development certificates and profiles must never sign App Store releases.
- TestFlight may validate the same release candidate, but App Store submission is a distinct approval action.
- Production credentials must not be available to pull-request workflows, forks, ordinary branch pushes, or developer laptops unless a documented break-glass procedure explicitly authorizes temporary access.
- No production signing secret may be stored in Git, repository variables, workflow YAML, build artifacts, chat, issue text, or ordinary shared drives.

### 5.1 Production Approval Gate

Before an App Store upload or submission:

1. CI and required quality/security checks pass for the exact commit.
2. The Release Manager confirms version/build number, Bundle Identifier, environment, and release notes.
3. The Security/DevOps Owner confirms signing assets are valid and the workflow used the `ios-production` environment.
4. The Product Release Approver gives explicit approval.
5. App Store submission is performed by the Release Manager or authorized backup.
6. The commit, build number, App Store Connect build ID, approvers, and result are recorded without secret values.

Emergency releases follow the same technical signing controls. Urgency does not permit bypassing protected environments or committing credentials.

## 6. Certificate and Account Custody

### 6.1 Apple Account

- The Apple Developer Program enrollment must be organization-owned.
- The Account Holder must use an individually controlled Apple ID with multifactor authentication.
- Shared Apple IDs are prohibited.
- At least two Apple Admins provide operational backup.
- Account recovery contacts, recovery methods, and Account Holder succession instructions belong in the organization's secure password manager/access register, not Git.
- The Account Holder is responsible for membership renewal and agreement acceptance; the Security/DevOps Owner tracks the operational deadline.

### 6.2 Creation and Revocation Authority

- Development certificates: authorized iOS Maintainers may allow Xcode to create/manage them within organization policy.
- Distribution certificates, profiles, and team API keys: only the Account Holder or an Apple Admin may create or revoke them, with the Security/DevOps Owner recording the change.
- Revocation requires impact review because one certificate may serve multiple active builds or workflows.
- Compromised credentials are revoked immediately; incident containment takes priority over release availability.

### 6.3 Approved Storage

| Asset | Approved storage |
| --- | --- |
| Developer private key/certificate | Developer's protected macOS Keychain/Xcode-managed storage |
| Distribution `.p12` and password | Organization secret manager/password-manager vault; encrypted backup with restricted access |
| Provisioning profile | Organization secret manager and/or protected CI environment secret |
| App Store Connect `.p8` key | Organization secret manager; protected CI environment secret for authorized workflow |
| Key ID, Issuer ID, Team ID | Protected CI configuration; may be repository variables only after security review confirms they are non-secret identifiers |
| Recovery codes/account recovery material | Restricted password-manager vault accessible only to Account Holder and designated backup |
| Inventory metadata | Private access register: purpose, owner, fingerprint/ID, creation, expiry, storage location, and last validation |

## 7. Renewal and Incident Process

### 7.1 Tracking and Reminders

The Security/DevOps Owner maintains the private credential inventory and reviews it monthly. Automated or calendar reminders must be set at:

- 90 days before certificate, profile, API-key policy, or membership expiry;
- 60 days before expiry;
- 30 days before expiry;
- weekly inside the final 30 days until renewal is verified.

The Release Manager is the renewal owner for distribution readiness; an Apple Admin is the operational backup. Apple Developer membership renewal remains the Account Holder's responsibility.

### 7.2 Renewal Procedure

1. Create or renew the asset using an authorized Apple role.
2. Generate dependent provisioning profiles when required.
3. update the secret manager and protected CI environment;
4. validate an unsigned build still passes;
5. validate a signed archive and TestFlight upload using a non-production release candidate;
6. revoke superseded material only after dependent workflows are confirmed migrated;
7. update the private inventory and this strategy or its implementation runbook if the process changed;
8. record the validation issue/PR and date without exposing secret values.

### 7.3 Expiry or Compromise Incident

If a signing asset expires unexpectedly:

1. pause signed distribution workflows;
2. identify affected certificates, profiles, apps, and recent builds;
3. create replacement material through an Apple Admin;
4. rotate CI secrets and rebuild profiles;
5. validate through TestFlight before resuming production;
6. document cause, impact, recovery, and prevention.

If an asset may be compromised, immediately disable affected workflows, revoke the credential/API key, rotate all dependent secrets, review audit logs, rebuild with new material, and follow the repository security-incident process. Never delay revocation merely to preserve a release schedule.

## 8. CI/CD Separation

| Pipeline | Signing | Trigger | Secrets | Current status |
| --- | --- | --- | --- | --- |
| `ios-xcode-validation.yml` | Explicitly unsigned | Relevant pull requests/manual dispatch | None | Active and passing |
| Future simulator validation | Unsigned | Pull requests/main | None | Planned |
| Future TestFlight distribution | Distribution signed | Protected manual/tag/release trigger | `ios-testflight` environment only | Blocked pending Apple setup and implementation issue |
| Future App Store production | Distribution signed | Protected release trigger after approvals | `ios-production` environment only | Blocked pending Apple setup and implementation issue |

The existing unsigned workflow must not be converted into a signed workflow. Signed distribution will use a separate workflow file so pull-request validation cannot accidentally gain access to Apple credentials.

### 8.1 Proposed Future Secret Names

These names are reserved proposals only. They must not be created until a dedicated signing implementation issue approves exact formats, scopes, environments, and rotation tests.

| Proposed secret | Purpose | Environment |
| --- | --- | --- |
| `IOS_DISTRIBUTION_CERTIFICATE_P12_BASE64` | Base64-encoded organization distribution certificate/private-key bundle | `ios-testflight`, separately provisioned in `ios-production` |
| `IOS_DISTRIBUTION_CERTIFICATE_PASSWORD` | Password protecting the `.p12` bundle | Same environment as certificate |
| `IOS_PROVISIONING_PROFILE_BASE64` | Base64-encoded App Store distribution provisioning profile | Environment-specific |
| `APP_STORE_CONNECT_API_KEY_P8_BASE64` | Base64-encoded least-privileged App Store Connect API private key | Environment-specific |
| `APP_STORE_CONNECT_KEY_ID` | API key identifier | Environment-specific |
| `APP_STORE_CONNECT_ISSUER_ID` | App Store Connect issuer identifier | Environment-specific |
| `APPLE_TEAM_ID` | Organization Apple Team ID | Environment-specific configuration |
| `IOS_TEMP_KEYCHAIN_PASSWORD` | Random password for the ephemeral CI keychain | Environment-specific |

TestFlight and production values must be stored independently even if an approved implementation initially uses the same organization certificate. GitHub Environment protection rules, not naming alone, enforce the boundary.

## 9. Security Rules

The following must never be committed:

- `.p12`, `.mobileprovision`, `.p8`, private-key, or exported Keychain files;
- certificate passwords, Apple ID passwords, app-specific passwords, session cookies, API private keys, or JWTs;
- Apple account recovery codes, multifactor-authentication codes, device recovery keys, or password-manager exports;
- Xcode `xcuserdata`, DerivedData, local Team selections, or machine-specific signing configuration;
- secrets encoded with Base64 or placed in `.env`, workflow YAML, documentation, issues, logs, screenshots, or build artifacts.

Required controls:

- Use a secure password manager/secret manager and protected CI environment secrets.
- Give Apple and GitHub roles the least privilege needed.
- Require multifactor authentication for human Apple accounts.
- Prefer short-lived CI access and ephemeral keychains.
- Restrict signed workflows from forks and untrusted pull requests.
- Mask secrets in logs and avoid commands that print decoded credentials.
- Review access quarterly and immediately when personnel or vendors leave.
- Record creation, rotation, revocation, and recovery tests in the private inventory.

## 10. Final Decision Table

| Area | Decision | Owner | Status | Future issue required? |
| --- | --- | --- | --- | --- |
| Simulator development | Any contributor with Mac/Xcode; unsigned | iOS Maintainer | Available | Optional simulator-CI issue |
| Physical iPhone development | Organization team, individual Apple IDs, local automatic signing allowed | iOS Maintainer + Apple Admin | Blocked: no organization team documented | Yes |
| Apple Developer membership | Organization-owned; one Account Holder and at least two Admins | Apple Account Holder | Not configured/documented | Yes |
| Bundle Identifier registration | Register `com.yeshmishak.app` to organization team | Apple Admin | Approved identifier; Apple registration unverified | Yes |
| TestFlight signing | Protected, reproducible distribution signing; API-key upload preferred | Release Manager + Security/DevOps Owner | Not configured | Yes |
| App Store Connect ownership | Organization-owned app record | Apple Account Holder | Not documented as created | Yes |
| Production signing | Separate protected environment and explicit release approvals | Release Manager + Product Release Approver | Not configured | Yes |
| Certificate custody | Secret manager, encrypted restricted backup, private inventory | Security/DevOps Owner | Policy approved; assets absent | Yes |
| Renewal | Monthly inventory review; 90/60/30-day and weekly reminders | Release Manager + Apple Admin backup | Process approved; tooling not configured | Yes |
| Unsigned CI | Keep existing Xcode validation unsigned | iOS Maintainer | Active and passing | No |
| Signed CI | Separate workflow; GitHub Actions preferred; protected environments | Security/DevOps Owner | Not implemented | Yes |
| Security/rotation | Least privilege, MFA, immediate revocation, documented rotation | Security/DevOps Owner | Policy approved | Yes, for implementation/runbook |

## 11. Implementation Gates

ISSUE-209 approves strategy only. The first signing implementation issue must not proceed until it can name or privately register the Account Holder, Apple Admins, Release Manager, and Security/DevOps Owner. It must also define rollback, verify secret-store access, and demonstrate that no credential reaches Git or pull-request workflows.

Recommended future issue sequence:

1. Enroll/verify organization Apple Developer Program membership and role assignments.
2. Register App ID and App Store Connect record for `com.yeshmishak.app`.
3. Configure physical-device development signing without committing machine settings.
4. Implement protected TestFlight signing and upload workflow.
5. Validate rotation/recovery and document the operational runbook.
6. Implement production App Store workflow with protected approval gates.

## 12. References

- [Apple Developer Program roles](https://developer.apple.com/help/account/access/roles)
- [App Store Connect build uploads](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/)
- [App Store Connect API access and keys](https://developer.apple.com/help/app-store-connect/get-started/app-store-connect-api)
- `docs/ios-development-environment.md`
- `docs/mobile-build-strategy.md`
- `docs/mobile-configuration-strategy.md`
- `.github/workflows/ios-xcode-validation.yml`
