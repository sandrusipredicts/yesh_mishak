# Secure Storage Failure Handling Strategy (ISSUE-232)

## 1. Purpose

Define the required application behavior for every secure-storage failure mode: storage unavailable, read failure, write failure, and delete failure. This document is strategy only — no code changes. It codifies the failure behavior already implemented in ISSUE-229 (secure token storage, PR #782), ISSUE-230 (secure session restoration, PR #783), and ISSUE-231 (secure logout cleanup, PR #784), identifies the gaps that remain, and defines the implementation requirements for ISSUE-233.

Baseline documents: `docs/secure-storage-architecture.md` (ISSUE-227), `docs/secure-storage-technology-selection.md` (ISSUE-228), `docs/authentication-storage-audit.md` (ISSUE-226).

## 2. Scope and non-goals

- Applies to the Android (Capacitor) native app and the web build. The storage owner is `frontend/src/api/sessionStorage.js`; the secure tier is `@aparajita/capacitor-secure-storage` v8 (Android Keystore-backed, AES-GCM values in `WSSecureStorageSharedPreferences`).
- iOS is out of scope for execution and validation, per the repository's platform policy. The strategy is written platform-agnostically so it can be adopted for iOS later without redesign.
- No backend changes, no runtime code changes, no tests in this issue. Implementation happens in ISSUE-233.

## 3. Guiding principle: fail closed

When the true authentication state is uncertain, the application must behave as if the user is **not** authenticated. A user who is wrongly logged out can log in again; a session that is wrongly kept alive is a security defect. Every rule below derives from this principle.

## 4. Failure mode catalogue and required behavior

### 4.1 Storage unavailable

| # | Scenario | Detection | Required behavior |
| --- | --- | --- | --- |
| U1 | Native secure storage plugin unavailable (module fails to load, plugin not registered) | Dynamic `import()` or plugin call throws at init | Start logged out. Clear cached user metadata. Show the login screen. Emit `secure_storage.unavailable`. Do not fall back to any web storage tier for the token. |
| U2 | Unsupported platform/runtime (native APIs missing on a platform build) | `Capacitor.isNativePlatform()` false on a native build, or plugin reports unsupported | Same as U1. On the web build this is not a failure: the web build intentionally uses the temporary web fallback tier defined by the architecture (section 16 of ISSUE-227) — that is a platform decision, never a failure fallback. |
| U3 | Permission/system-level storage issue (Keystore unavailable, prefs unwritable, disk full) | Plugin call throws with a system error | Same as U1. Additionally attempt a best-effort remove of the token entry so no stale ciphertext outlives the failure. |
| U4 | Android WebView/native bridge unavailable (bridge not injected, `nativePromise` missing) | Plugin proxy call rejects or never resolves | Same as U1, plus the timeout rule R5 (section 7) so a dead bridge cannot hang the app on the "checking session" screen forever. |

Current state: U1–U3 are handled by `initSessionStorage()` fail-closed paths (ISSUE-229/230). U4's hang case is **not** handled — there is no timeout around the initial secure-storage read. This is Gap G1 for ISSUE-233.

### 4.2 Read failure

| # | Scenario | Detection | Required behavior |
| --- | --- | --- | --- |
| R1 | Secure storage read throws | `getItem` rejects | Treat as "no session": clear user metadata, attempt best-effort `removeItem` of the token entry, start logged out. Emit `secure_storage.read_failure`. Never retry-loop a failing startup read. |
| R2 | Stored token cannot be decrypted (Keystore key rotated/invalidated, device credential change) | Plugin decrypt error on `getItem` | Same as R1. The ciphertext is garbage without the key — remove it. |
| R3 | Corrupt secure-storage value (parse error, truncated data) | Plugin returns error or malformed value; JWT subject cannot be parsed | Same as R1. The existing behavior (validated in `session-restoration.spec.js`, "corrupted token fails closed") also clears the corrupt entry from disk. |
| R4 | Timeout / hanging read | Read promise does not settle within the startup deadline | Treat as R1 after the deadline (rule R5, section 7). The UI must leave the "checking session" state and render the login screen. Emit `secure_storage.read_timeout`. |
| R5 | Unexpected null/empty value | `getItem` resolves with null/empty while metadata suggests a session existed | Not an error: treat as logged out. Clear orphaned user metadata so no half-session remains. No warning to the user. |

Current state: R1–R3 and R5 are implemented (ISSUE-229/230). R4 is Gap G1.

### 4.3 Write failure

| # | Scenario | Detection | Required behavior |
| --- | --- | --- | --- |
| W1 | Token save fails after login | `setItem` rejects in `setToken` | The server-side login succeeded, so keep the session **in memory only** for the current run. Retry the write once (rule table, section 7). If the retry fails: emit `secure_storage.write_failure`, and surface a non-blocking notice that the session will not survive an app restart (ISSUE-233). Never write the JWT to localStorage or sessionStorage instead. |
| W2 | Partial write uncertainty (write rejected but state on disk unknown) | `setItem` rejects ambiguously | Assume the worst of both worlds: the disk value is untrusted. Attempt a best-effort `removeItem`, then behave as W1 (in-memory session only). |
| W3 | Migration from legacy localStorage fails (secure write of the migrated token rejects) | Migration path in `initSessionStorage()` | Fail closed and delete the plaintext copy anyway: the plaintext localStorage token is removed **regardless** of migration success, the in-memory session is dropped, and the app starts logged out. A lost session is acceptable; a plaintext JWT surviving in the WebView is not. Emit `secure_storage.migration_failure`. (Implemented in ISSUE-229.) |
| W4 | Secure write succeeds but a verification read fails | Post-write `getItem` mismatch | Routine read-back verification is **not required**: the plugin's promise contract already reports write failure, and a verify-read doubles Keystore work on every login. If a verify-read is ever added (debug builds only), a mismatch is treated as W2. |

Current state: W1 exists without the retry and without the user-visible notice (silent `console.warn` only) — Gap G2. W3 is implemented.

### 4.4 Delete failure

| # | Scenario | Detection | Required behavior |
| --- | --- | --- | --- |
| D1 | Logout cleanup fails (secure `removeItem` rejects) | `clearToken()` during user logout | Complete **all other cleanup anyway** (in-memory token, localStorage metadata, legacy keys, web sessionStorage), render the logged-out UI, retry the remove once, and if it still fails: propagate the error and show the logout warning banner (`auth.logoutCleanupError`) telling the user cleanup did not fully succeed. Never pretend logout fully succeeded. (Implemented in ISSUE-231, PR #784.) |
| D2 | 401/403 cleanup fails | `clearSession()` from the response interceptor | Same cleanup-everything-first behavior. The UI still drops to logged out (the 401 already invalidated the session server-side). The failure is logged and emitted as `secure_storage.delete_failure`; no banner is required because the user did not initiate the action — the next launch's restoration validation will reject the stale token server-side. |
| D3 | Corrupt token cleanup fails (removing a corrupt entry after R2/R3 also fails) | Cleanup `removeItem` rejects inside the read-failure path | Already-failed-closed state stands (logged out, metadata cleared). Log the cleanup failure; do not block startup on it. |
| D4 | Fail-closed guarantee | — | In every delete-failure case the **in-memory and UI state must already be unauthenticated** before any error is surfaced. Storage cleanup failure may leave ciphertext behind; it must never leave a logged-in UI behind. |

## 5. Security invariants (non-negotiable)

1. **Never store the JWT in localStorage or sessionStorage as a fallback** for any secure-storage failure, on any platform. The web build's temporary web-fallback tier is a pre-existing platform decision (ISSUE-227 section 16), not a failure response, and it is never used by the native app.
2. **Never log token values** — not plaintext, not ciphertext, not prefixes, not lengths derived for debugging in production. Log only error objects and event names.
3. **Never keep authenticated UI when secure session state is uncertain.** Uncertainty resolves to logged out (section 3).
4. **Auth state must fail closed** in every path: init, restoration, resume revalidation, login, logout, interceptor cleanup.
5. **Logout must win over in-flight validation.** A logout invalidates any pending session validation (epoch guard from ISSUE-231); a late `/games/me` success must never restore the user, and request deduplication must never hand back stale authenticated state.
6. A failure in one cleanup step must not abort the remaining cleanup steps (implemented as try/finally ordering in `clearSession()`).

## 6. User-facing behavior matrix

| Situation | Warning banner | Force logout | Silent retry | Require login again |
| --- | --- | --- | --- | --- |
| Storage unavailable at startup (U1–U4) | No banner — user simply sees the login screen | State is already logged out | No | Yes |
| Read failure at startup (R1–R4) | No banner | State is already logged out | No (single cleanup attempt only) | Yes |
| Write failure after login (W1/W2) | Non-blocking notice: session won't survive restart (ISSUE-233) | No — server login succeeded; keep in-memory session | One retry of the write | Only after next app restart |
| Migration failure (W3) | No banner | Yes — start logged out | No | Yes |
| Logout delete failure (D1) | Yes — logout warning banner (exists today) | UI is already logged out | One retry of the remove | Yes (user is logged out) |
| Interceptor cleanup failure (D2) | No banner | UI drops to logged out | One retry inside `clearToken` | Yes |

Rules of thumb: a banner is shown only when the **user initiated** the action that partially failed (logout) or when their expectation will silently break later (login persistence). Failures the user cannot act on at startup resolve silently to the login screen — the login screen *is* the message.

## 7. Retry strategy

| Operation | Retries | Backoff | Rationale |
| --- | --- | --- | --- |
| Startup read (`getItem`) | 0 (one best-effort cleanup `removeItem` after failure) | — | Blocking launch on a retry loop harms startup; next launch retries naturally. |
| Login write (`setItem`) | 1 immediate retry | None | Transient Keystore contention is the plausible failure; one retry is cheap. |
| Logout/cleanup delete (`removeItem`) | 1 immediate retry | None (implemented in ISSUE-231) | Deleting is the security-critical direction; one extra attempt before surfacing. |
| Migration write | 0 | — | Migration re-runs on next launch by design; plaintext is deleted regardless. |

- **Maximum one retry, immediate, no backoff loops.** These are local IPC calls, not network calls: either the second attempt works or the failure is systemic and looping delays the fail-closed outcome.
- **Startup deadline (new, Gap G1):** the entire secure-storage init read must settle within a fixed deadline (recommended 5 seconds); on expiry treat as read failure R4. The deadline guards the hanging-bridge case that promise rejection can never catch.
- **When retry is unsafe:** never retry a `setItem` after a logout has begun (the logout epoch must gate any pending write), and never retry an operation whose success would resurrect state the user asked to destroy. Delete retries are always safe — deleting twice is idempotent.

## 8. Observability

- **Allowed:** event name, failure stage (init / restore / login / logout / interceptor), the thrown error object (message + stack), platform, retry count.
- **Never logged:** token values (plain or encrypted), decoded JWT claims, storage values of any auth key, user password material. PII (name/email) must not be added to failure logs.
- **Suggested event names** (matching the backend's `event=` convention, e.g. `auth.logout.failure`):
  - `secure_storage.unavailable`
  - `secure_storage.read_failure` / `secure_storage.read_timeout`
  - `secure_storage.write_failure` / `secure_storage.write_retry_success`
  - `secure_storage.delete_failure` / `secure_storage.delete_retry_success`
  - `secure_storage.migration_failure`
- Today these exist only as `console.warn` calls visible via `adb logcat`/WebView devtools. That is acceptable for the debug phase; ISSUE-233 should centralize them behind one helper so event names are consistent and greppable.
- **Debug-only evidence rules:** during device validation, evidence of token presence/absence is collected from *outside* the app (`run-as` on `WSSecureStorageSharedPreferences.xml`, storage snapshots with JWT-pattern scans that redact values) — never by adding token logging to app code. Validation tooling must print at most a boolean ("JWT-like value present: yes/no") or a redacted prefix, never a full token.

## 9. Testing strategy (for ISSUE-233 and onward)

1. **Unit/regression (Playwright, existing mock pattern):** extend the `nativePromise` Capacitor mock used by `session-restoration.spec.js` and `logout-cleanup.spec.js` to reject or hang per scenario:
   - unavailable: plugin proxy missing / import failure → app lands on login screen, no crash;
   - read failure and corrupt value → fail closed, cleanup attempted, login screen (exists today);
   - read hang → app leaves "checking session" within the deadline and lands on login screen (new, G1);
   - write failure after login → session usable now, notice shown, relaunch starts logged out, no JWT in web storage (new, G2);
   - migration failure → plaintext removed, logged out (exists);
   - delete failure at logout → retry observed (2 attempts), warning banner, UI logged out (exists).
2. **Race-condition tests:** logout during in-flight validation, late `/games/me` success, resume revalidation after logout, dedup staleness — all exist in `logout-cleanup.spec.js`; keep them green as failure handling is added (failure paths must respect the same epoch guard).
3. **No-token-leakage checks:** every failure-path test asserts a JWT-pattern scan (`^eyJ…`) over all localStorage and sessionStorage keys returns empty, and asserts no token value appears in captured console output.
4. **Android physical validation checklist (Samsung, debug APK):** repeat the ISSUE-231 method — CDP-driven UI plus `run-as` inspection of `WSSecureStorageSharedPreferences.xml` — for: login with secure write verified on disk; simulated failure builds are not required on-device, but relaunch, force-stop, background/resume, and device-restart flows must stay logged out after any induced failure; logcat reviewed to confirm no token value was printed.

## 10. Acceptance criteria for ISSUE-233 (implementation)

ISSUE-233 converts this strategy into code. It is done when:

1. **G1 — startup deadline:** the secure-storage init/read path has a settle deadline (recommended 5s); expiry behaves exactly like read failure R1 and emits `secure_storage.read_timeout`. The app can never remain on the "checking session" screen because of a hung bridge.
2. **G2 — login write failure:** `setToken` retries once; on final failure the session remains in-memory-only, a non-blocking user notice is shown, and `secure_storage.write_failure` is emitted. No web-storage fallback is introduced.
3. **Centralized failure events:** all secure-storage failure logging goes through one helper enforcing the event names in section 8 and the never-log list.
4. All behaviors in the section 4 tables that are marked implemented remain unchanged and their existing regression tests stay green; new behaviors get the regression tests listed in section 9.1.
5. Scope discipline: frontend `sessionStorage.js`/`App.jsx` (and locale files for the notice) only — no backend, no iOS, no Android-native file changes, no new packages.

**GO/NO-GO validation rules for ISSUE-233:**

- GO only if: all section 9.1 regression tests pass; lint/build/Android build pass; Samsung physical validation confirms fail-closed outcomes for relaunch/force-stop/resume/restart after failures; JWT-pattern scans are empty in every failure state; no token value appears in any log.
- NO-GO if any failure mode leaves authenticated UI with uncertain storage state, if any path writes a JWT to web storage, if any retry loops beyond the section 7 limits, or if any check above is missing, flaky, or unproven.

## 11. Traceability

| Requirement source | Covered in |
| --- | --- |
| Storage unavailable scenarios | Section 4.1 |
| Read failure scenarios | Section 4.2 |
| Write failure scenarios | Section 4.3 |
| Delete failure / fail closed | Section 4.4 |
| Security invariants | Section 5 |
| User-facing behavior | Section 6 |
| Retry strategy | Section 7 |
| Observability | Section 8 |
| Testing strategy | Section 9 |
| ISSUE-233 acceptance criteria | Section 10 |
