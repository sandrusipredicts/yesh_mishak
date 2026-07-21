# Data safety inventory — release-owner worksheet

Status: **manual verification required before Play submission**.

This inventory maps observed product behavior to likely Google Play Data safety categories. It is not legal advice and is not a completed console declaration. Validate the installed release build, backend, production configuration, retention jobs, and provider contracts.

| Data type / behavior | Observed use | Likely purpose | Collection/sharing decision to verify |
| :--- | :--- | :--- | :--- |
| Name, username, email, phone | Account creation, profile, authentication, support | Account management, app functionality, security | Collected; confirm optional fields and service-provider treatment |
| Google account identifier and profile data | Google Sign-In/account linking | Account management, security | Collected when Google login is used |
| Password/authentication data | Manual authentication; server-side credential handling | Account management, security | Confirm hashing, transport, retention, and Data safety category |
| City and deliberately saved coordinates | Map, field submission, location-based notification preferences | App functionality, personalization | Collected in saved workflows; distinguish from live on-device location |
| Live foreground device location | Centering/finding nearby fields | App functionality | Normally processed on-device; verify network calls and telemetry do not transmit it unexpectedly |
| Background location | Android manifest intentionally omits it | Not used | Declare not collected/used only after device verification |
| Game/field activity, participation, reports | Core product records and moderation | App functionality, safety, analytics | Collected; some data is visible to other users |
| Field photos/media | Camera/photo-picker flows may submit field images | App functionality, moderation | Confirm shipped endpoints/storage and disclose photos if enabled |
| Push token, installation/device identifiers, platform | Push delivery and installation routing | App functionality | Collected; identify Firebase/provider handling |
| Product interaction analytics | First-party analytics events | Analytics, app functionality | Collected; verify event properties contain no undeclared PII or precise location |
| Crash logs and diagnostics | Sentry/technical monitoring configuration | Analytics, security, diagnostics | Collected when enabled; document redaction and retention |
| Notification preferences | Personalized notifications | App functionality, personalization | Collected |
| Calendar event insertion | User-triggered device calendar action | App functionality | Verify write-only behavior; do not declare calendar reading if none occurs |
| Shared links | User-triggered system share sheet | App functionality | Verify share analytics record mechanism/outcome only, not recipient/content beyond approved fields |

## Required answers and evidence

- [ ] List every production SDK and backend provider that receives user or device data.
- [ ] Confirm whether each transfer qualifies as collection and/or sharing under current Play definitions and exemptions.
- [ ] Confirm collection is required or optional per data type and that the UI matches the answer.
- [ ] Confirm each purpose: app functionality, analytics, developer communications, advertising/marketing, fraud/security/compliance, personalization, or account management.
- [ ] Confirm data is encrypted in transit across mobile, web, API, storage, monitoring, maps, auth, and push paths.
- [ ] Confirm account-deletion requests are operational, identity-verified, executed, and cover associated data with documented exceptions.
- [ ] Confirm retention periods, especially first-party analytics and crash diagnostics.
- [ ] Confirm no advertising ID access or ads SDK in the release bundle.
- [ ] Compare the final console answers with the public privacy policy and an intercepted release-build network trace.

Any discrepancy is a release blocker until code/configuration, privacy text, or console answers are aligned and approved.
