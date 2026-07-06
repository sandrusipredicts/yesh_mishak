# Authentication Security Review

## Scope
- **Audited Commit**: `2b7176a` (main branch)
- **Tracking Reference**: ISSUE-246 / GitHub issue #335
- **Areas Inspected**:
  - backend auth JWT issuance/validation
  - Google login
  - logout/revocation
  - admin authorization
  - CORS
  - logging/token leaks
  - frontend session storage
  - restore/fail-closed behavior

## Executive Verdict
- **P0**: none.
- **Production Code Changes**: No production code changes required for ISSUE-246.
- **Deliverable**: ISSUE-246 is a documentation-only audit and report deliverable.

## Existing Protections Already Implemented
- **Google login**: ID token is verified server-side using Google library; signature, expiry, and audience are checked against the single configured web client ID. email and sub claims are required. email_verified=true is enforced with 403. Login is rate-limited. Google ID token is exchange-only and is not stored or logged.
- **JWT issuance**: HS256 with JWT_SECRET required from environment. App should not boot with missing JWT_SECRET. Claims include sub/email/iat/exp. Token TTL is 7 days. Expired/invalid tokens return 401.
- **Revocation**: /auth/logout sets users.tokens_valid_after and fails closed if the write fails. Authenticated requests compare token iat against tokens_valid_after. In-process user cache is invalidated on logout. ISSUE-245 Android validation proved revoked token -> real backend 401 -> fail-closed cleanup.
- **Per-request checks**: user must exist in DB. banned/suspended users receive 403. Admin role is read from DB, not JWT. Admin routes are protected with require_admin.
- **Password auth**: bcrypt with per-hash salt. Neutral invalid-credentials response. IP rate limits and progressive-delay brute-force protection. Failure logs do not carry username/email.
- **Token storage boundaries**: Android uses Keystore-backed secure storage only. No plaintext JWT in WebView storage. Restore fails closed on corrupt, timeout, or 401. Web-to-native migration does not leave plaintext behind. Logout clears secure/local/session/memory/legacy storage with epoch guard.
- **Leak hygiene**: no console token logging found. No tokens in URLs. Backend logs event names, booleans, and user IDs; auth headers are not logged.
- **CORS**: explicit allowlist from environment. No wildcard-with-credentials. https://localhost is used for Capacitor WebView and is origin-bound. Bearer-header auth means CSRF risk is not cookie-based.
- **Platform**: Android auto-backup disabled so storage cannot resurrect via backup. CodeQL runs in CI.

## Confirmed Risks / Gaps
- **P1**: Account linking via email-only matching. find_or_create_google_user matches by email and does not check/backfill google_sub. Manual registration has no email verification. This creates pre-registration hijack / silent implicit linking risk. Already documented in [docs/account-linking-strategy.md](file:///c:/Users/orel1/yesh_mishak/docs/account-linking-strategy.md) and should be fixed under ISSUE-244.
- **P1 accepted/temporary**: Web browser tier stores JWT in plaintext localStorage. This is XSS-exposed and is a documented temporary compatibility tier. Native Android is already hardened. Web hardening is deferred but should stay visible.
- **P2**: JWT has no aud/iss claims. Additive hardening against token confusion if the secret is ever shared with another service.
- **P2**: Revocation lag up to 300 seconds across multiple workers or replicas because the user cache is in-process.
- **P2**: Dev localhost origins are appended to CORS in production unconditionally. Low impact under bearer auth, but should be cleaned later.
- **P2**: bcrypt 72-byte truncation. Passwords up to 128 characters are accepted but bcrypt truncates at 72 bytes.
- **P2**: Email PII is included in JWT payload.
- **P2**: Frontend axios client has no HTTP timeout, so hung auth calls may not settle.
- **Info/accepted**: check-username and check-email are enumeration-by-design but rate-limited. 7-day token without refresh rotation is an accepted scope decision.

## False Positives / Already Handled
- Plaintext JWT on Android: not present.
- Token/header logging leaks: greps clean.
- Unprotected admin endpoints: admin routes covered by require_admin.
- CSRF: no cookie auth.
- Default/weak JWT secret: boot fails without env secret.
- 401/corrupt-token fail-open: handled fail-closed.
- Stale-response session races: guarded.
- Backup-restored tokens: backup disabled and secure storage does not survive uninstall.

## Recommended Minimal Fixes Ranked P0/P1/P2
- **P0**: none.
- **P1**:
  1. Implement ISSUE-244 account-linking strategy: user_identities, sub-first matching, no silent link into unverified manual accounts.
  2. Add email verification to manual registration as a separate issue or as part of the account-linking security track.
- **P2**:
  1. Add aud and iss claims to JWT issue/decode.
  2. Gate dev CORS origins by environment.
  3. Document or shrink AUTH_USER_CACHE_TTL_SECONDS for multi-worker deployments.
  4. Cap password length at 72 bytes or pre-hash safely.
  5. Remove email claim from JWT payload.
  6. Add axios timeout.

## Files Likely Affected if Future Fixes are Approved
- **ISSUE-244/account linking**:
  - [backend/app/auth/google.py](file:///c:/Users/orel1/yesh_mishak/backend/app/auth/google.py)
  - [backend/app/api/auth.py](file:///c:/Users/orel1/yesh_mishak/backend/app/api/auth.py)
  - migration for user_identities
  - frontend login-methods UI
- **aud/iss**:
  - [backend/app/auth/jwt.py](file:///c:/Users/orel1/yesh_mishak/backend/app/auth/jwt.py)
- **CORS gating**:
  - [backend/app/main.py](file:///c:/Users/orel1/yesh_mishak/backend/app/main.py)
- **Password cap**:
  - [backend/app/auth/passwords.py](file:///c:/Users/orel1/yesh_mishak/backend/app/auth/passwords.py)
- **Axios timeout**:
  - [frontend/src/api/client.js](file:///c:/Users/orel1/yesh_mishak/frontend/src/api/client.js)

## Explicit No-Touch Areas
- iOS excluded.
- [frontend/src/api/sessionStorage.js](file:///c:/Users/orel1/yesh_mishak/frontend/src/api/sessionStorage.js) and secure-storage plumbing excluded because no defect was proven.
- Map, marker, notifications, UX excluded.
- No style refactor of auth/session code.
- No token issuance changes beyond future additive hardening.

## Product Gate Note
- Android/code validation for prior session lifecycle is **PASS**.
- Final Product DONE remains gated by ISSUE-240 iPhone validation if project policy requires it.

## Final Verdict
The authentication implementation exhibits robust security practices overall. The verified mechanisms fail closed, rate limit sensitive actions, and restrict token usage and storage boundaries appropriately. While there are actionable areas for hardening (specifically around account linking and token verification claims), there are no P0 security defects. ISSUE-246 is completed with this audit report, and no production code changes are required.
