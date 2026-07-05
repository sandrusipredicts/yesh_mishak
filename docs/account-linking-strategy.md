# Account Linking Strategy

**Issue:** ISSUE-243 (#332)
**Status:** Strategy document — no implementation. Implementation is ISSUE-244 (#333).
**Date:** 2026-07-05
**Related docs:** [authentication-flow-audit.md](authentication-flow-audit.md), [native-authentication-architecture.md](native-authentication-architecture.md), [session-lifecycle.md](session-lifecycle.md)

---

## 1. Problem statement

Users may authenticate with more than one method: email/password (already implemented), Google Sign-In (already implemented, web + Android native), and future providers (e.g. Apple). Today the two existing methods coexist without an explicit linking model: Google login matches accounts **by email only**, which is an implicit, silent form of account linking with no provider-identity binding. This document defines the canonical strategy for how login methods attach to, detach from, and conflict with user accounts, so that ISSUE-244 can implement it and future providers can be added without redesign.

## 2. Current authentication model

Grounded in the code as of main `042f01f`:

- **Backend:** FastAPI + Supabase Postgres. Single `users` table holds identity: `id` (UUID, PK), `email`, `name`, `username`, `phone_number`, `password_hash`, `google_sub`, `last_login`.
- **App session:** backend-issued JWT (HS256, 7-day TTL, `sub` = internal user id, `email` claim), with server-side revocation on logout (`jwt_token_revocation.sql`).
- **Manual method:** `POST /auth/register` (email + username + password; **email ownership is NOT verified**) and `POST /auth/login` (email-or-username + password). Registration fails closed on duplicate email/username (`EMAIL_TAKEN` / username taken).
- **Google method:** `POST /auth/google` verifies the Google ID token against the single web OAuth client ID audience (`app/auth/google.py`). It requires `email` + `sub` claims and **rejects `email_verified != true` with 403 `EMAIL_NOT_VERIFIED`** (already implemented). It then calls `find_or_create_google_user`:
  - Lookup is `users.email == token.email` — **`google_sub` is never used for lookup and never backfilled on match.**
  - `google_sub` is stored only when a brand-new user row is inserted.
  - Google-created users have `username`, `phone_number`, `password_hash` = null.
- **Implication:** a manually registered account whose (unverified) email later matches a Google login is silently "linked" by email today; the resulting account has a password from registration and a Google path in, but no `google_sub` binding, no user awareness, and no audit trail of a link event.

## 3. Source of truth for user identity

**The internal `users.id` (UUID) is and must remain the canonical identity.** Everything else — email, username, provider subjects — is a *credential or claim attached to* that identity, never the identity itself.

- The app JWT `sub` is the internal user id; linking/unlinking login methods must never change it.
- Games, participants, notifications, and all domain data reference `users.id` and are unaffected by login-method changes.
- Email is a mutable, reusable, user-facing attribute (Google Workspace domains recycle addresses; users change emails). It must not be treated as a permanent key.

## 4. Account identifier strategy

Ranked strength of identifiers, strongest first:

| Rank | Identifier | Stability | Allowed use |
|---|---|---|---|
| 1 | Internal `users.id` | Permanent | Canonical identity, JWT `sub`, all FKs |
| 2 | Provider subject (`google_sub`, future `apple_sub`) | Permanent per provider account | Login-method matching (primary), linking |
| 3 | Verified email (provider-asserted `email_verified=true`) | Mutable | Conservative fallback matching only, per rules in §6 |
| 4 | Unverified email (manual registration today) | Unproven | **Never** a basis for matching or linking |
| 5 | Username / phone | Mutable, optional | Never used for linking |

**Provider subject IDs must be treated as stronger identifiers than email.** Login-method resolution must check the provider subject first, and only fall back to verified email under the rules below.

## 5. Provider identity model

Recommended target model: a dedicated **`user_identities`** table rather than adding one column per provider to `users`:

| Column | Notes |
|---|---|
| `id` | UUID PK |
| `user_id` | FK → `users.id`, cascade on user deletion |
| `provider` | `'google'`, `'apple'`, ... |
| `provider_subject` | The provider's stable `sub` |
| `email_at_link` | Provider email captured at link time (Apple only reveals email once) |
| `email_verified_at_link` | Boolean, from provider claim |
| `created_at`, `last_used_at` | Timestamps |

Constraints:

- **UNIQUE (`provider`, `provider_subject`)** — one provider account can belong to at most one user. This is the mechanical enforcement of the fail-closed conflict rule.
- UNIQUE (`user_id`, `provider`) — v1 policy: at most one identity per provider per user (simplifies unlink UX; can be relaxed later).
- The password method is represented by `users.password_hash IS NOT NULL`, not by an identities row.
- Migration path: backfill `user_identities` from existing `users.google_sub`, then treat `users.google_sub` as deprecated/read-only until removed. (Migration itself is ISSUE-244 scope.)

## 6. Linking rules

Login-method resolution for a provider token (evaluated in order):

- **L1 — Subject match (primary):** an identity row matches (`provider`, `provider_subject`) → log the user in. Email differences are ignored (email may have changed at the provider); optionally refresh stored metadata.
- **L2 — Verified-email fallback (conservative auto-link):** no subject match, and the provider asserts `email_verified=true`, and exactly one user has that email, and that user has **no existing identity for this provider** → auto-link is permitted **only if** the target account's email ownership is itself trustworthy for this email. Because manual registration does not verify email today, the v1 conservative rule is:
  - Target account was **created by a provider** (email already provider-verified) → auto-link allowed; create the identity row, notify the user.
  - Target account is **manual (password) with unverified email** → do **not** silently auto-link. Require proof of account ownership: the user must sign in with their password (or complete email verification, once that exists) and then confirm the link. Until then, the provider login is rejected with an explicit "account exists — sign in to link" response, not a silent merge and not a duplicate account.
- **L3 — No match:** create a new user + identity row (current new-user behavior, plus the identity row).
- **L4 — Explicit linking (authenticated):** a signed-in user adds a provider from settings. Requires an **active authenticated session**, and **strong re-authentication** (fresh provider token verified server-side; for adding a password, current-session re-auth). The new provider token must satisfy L-rules: subject not linked elsewhere, `email_verified=true` if email differs from the account email.
- **L5 — Subject binding backfill:** whenever L2 or L4 succeeds, the provider subject is bound immediately; all future logins resolve via L1. The current email-only matching path is retired.

**Automatic linking must be conservative:** when any condition above is uncertain (multiple email matches, unverified email, existing conflicting identity, provider didn't assert verification), fail closed to an explicit user-driven flow. Never link based only on unverified email. Never silently merge two existing user accounts — merging existing accounts is out of scope for automation entirely and, if ever needed, requires an explicit admin/user-safe flow with its own design.

## 7. Conflict rules

| Conflict | Rule |
|---|---|
| Provider subject already linked to another user | **Fail closed.** Reject with 409 `PROVIDER_ALREADY_LINKED`. Never re-point the identity, never merge. Message must not disclose the other account's email/identity. |
| Verified provider email matches user A, but requester is authenticated as user B (explicit link) | Allowed — email match is informational for L4; the subject binding is to B. The provider email is stored as `email_at_link` and does not overwrite B's account email. |
| Provider email matches multiple users | Fail closed to explicit flow; never auto-pick. (Should be prevented by unique email, but the rule stands defensively.) |
| Manual registration with an email already used by a Google account | Current behavior is correct: `EMAIL_TAKEN`, fail closed. The UX should point the user to Google sign-in / future "set password" flow instead. |
| Two concurrent link attempts for the same subject | The UNIQUE constraint arbitrates; the loser receives 409. |

## 8. Security requirements

1. Internal user ID remains canonical; linking never rewrites domain data or JWT `sub` semantics.
2. Provider subject > verified email > everything else (§4); email matching only with `email_verified=true` asserted by the provider (already enforced for Google — keep).
3. Adding a login method requires an authenticated session **plus** strong re-authentication (fresh provider proof, or password re-entry). Possession of a valid 7-day JWT alone is not sufficient for linking on a possibly shared/stolen device.
4. Never link on unverified email; never silently merge existing accounts; fail closed on already-linked subjects (§6, §7).
5. Pre-registration hijack defense: because manual registration doesn't verify email, an attacker can register `victim@example.com` with their own password before the victim's first Google login. Rule L2 (no silent auto-link into unverified manual accounts) is the mitigation; long-term fix is email verification for manual registration (out of scope here).
6. Link/unlink are session-sensitive events: on unlink, revoke outstanding sessions established via that method where identifiable, or all sessions as the simple v1; on link, notify (see §11/§12).
7. Provider tokens remain exchange-only: never stored, never logged (existing rule — keep). Identity rows store subjects, not tokens.
8. Rate-limit link/unlink endpoints like the existing auth endpoints.
9. Error responses must not leak whether an email or provider account exists beyond what the flow requires (align with existing neutral error handling from ISSUE-241).

## 9. Data model recommendation

- Add `user_identities` per §5 with both UNIQUE constraints; backfill from `users.google_sub`; deprecate the column afterwards.
- Add nothing else to `users` for providers — future providers = new rows, not new columns.
- Keep `password_hash` on `users` as the manual-method marker.
- A "login methods count" is derivable: `(password_hash IS NOT NULL) + COUNT(user_identities)` — this powers the unlink guard (§15, scenario 8).
- **No migration in this issue.** SQL lands with ISSUE-244.

## 10. Backend API recommendation

For ISSUE-244 (names indicative):

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /auth/google` (existing) | none | Login/registration; re-implemented as L1→L2→L3 resolution instead of email-only lookup |
| `GET /auth/methods` | session | List linked methods (provider, email_at_link masked, created_at) + whether password is set |
| `POST /auth/link/{provider}` | session + fresh provider token | Explicit link (L4); 409 on conflicts |
| `DELETE /auth/link/{provider}` | session + re-auth | Unlink; 409 `LAST_LOGIN_METHOD` if it would strand the account |
| `POST /auth/password` (set/change) | session + re-auth | Lets provider-only users add the manual method (enables scenario 4 safely) |

Backend remains the only component making linking decisions; clients never assert identity equivalence.

## 11. UX recommendation

- Settings → "Login methods" screen: list methods, add Google/Apple, set password, unlink with confirmation.
- L2-blocked login (provider login hits an unlinked manual account): show "An account with this email already exists — sign in with your password to connect Google", deep-linking to password login followed by a confirm-link step. Neutral wording, no account enumeration beyond the user's own email.
- Conflict (already linked elsewhere): neutral failure — "This Google account is already connected to a different user" — with support guidance; never reveal the other account.
- Unlink of last method: blocked with explanation and a shortcut to add another method first.
- Linking events trigger a notification (in-app now; email later when email infrastructure exists).

## 12. Audit/logging recommendation

Extend the existing structured auth logging (same conventions: event names, `attempt_id`, `user_id`, no token values, no raw emails where avoidable):

- `auth.link.start / success / failure` and `auth.unlink.start / success / failure` with `provider`, `user_id`, `error_code` (`PROVIDER_ALREADY_LINKED`, `LAST_LOGIN_METHOD`, `EMAIL_NOT_VERIFIED`, ...).
- `auth.login.method_resolution` recording which rule matched (L1/L2/L3) — this makes silent-linking regressions observable.
- Log provider subjects hashed or truncated, never raw ID tokens (consistent with existing hardening).
- Audit rows retained per existing log retention; identity rows removed on account deletion while audit history keeps the hashed subject for incident forensics.

## 13. Out-of-scope items

- Any implementation, migration, or config change — all of it is ISSUE-244 (#333) or later.
- Email verification for manual registration (flagged as the root fix for §8.5; separate issue).
- Apple Sign-In configuration and iOS work (iOS is excluded from the current workstream entirely).
- Admin-driven account merge tooling.
- FCM/push token lifecycle (tracked separately), Android backup policy (#796).

## 14. Future implementation checklist (ISSUE-244 input)

1. Create `user_identities` + constraints; backfill from `users.google_sub`.
2. Rewrite `find_or_create_google_user` as L1→L2→L3 resolution; backfill subject on L2; emit `auth.login.method_resolution`.
3. Implement `GET /auth/methods`, `POST /auth/link/google`, `DELETE /auth/link/google`, `POST /auth/password` with re-auth and rate limits.
4. Enforce unlink guard (`LAST_LOGIN_METHOD`).
5. Frontend "Login methods" settings UI + blocked-login link flow.
6. Tests: each scenario in §15, both directions, plus the 409 conflicts and unlink guard.
7. Session revocation on unlink.
8. Only then: retire email-only matching.

## 15. Scenario matrix

| # | Scenario | Current behavior (main `042f01f`) | Target strategy | Rule |
|---|---|---|---|---|
| 1 | Google login, new user | Email no-match → user created with `google_sub` | Same, plus identity row created | L3 |
| 2 | Google login, existing Google user | Matched **by email**; `google_sub` ignored | Matched by subject; email changes at Google don't break login | L1 |
| 3 | Manual account exists → Google login, same verified email | **Silently logs into the manual account** (implicit email link, no sub binding, no notice) | Blocked from silent link: user proves password, confirms link, subject bound; thereafter L1 | L2 (manual-target branch) |
| 4 | Google account exists → manual login attempt, same email | `/auth/login` fails (`password_hash` null); `/auth/register` fails `EMAIL_TAKEN` | Same fail-closed behavior; safe path is authenticated "set password" | L4 / §10 |
| 5 | Existing account + Google login with a *different* email | Creates a separate new user (email no-match) | Same for unauthenticated login (L3). To attach that Google identity to the existing account: explicit authenticated linking only | L3 / L4 |
| 6 | Provider account already linked to another user | Not detectable today (sub unused on lookup) | 409 `PROVIDER_ALREADY_LINKED`, fail closed, no merge, no disclosure | §7 |
| 7 | Provider email not verified | Google: rejected 403 `EMAIL_NOT_VERIFIED` (implemented) | Keep; also blocks L2/L4 email-based decisions for any provider | §6/§8 |
| 8 | Unlink the only login method | No unlink exists | Blocked with 409 `LAST_LOGIN_METHOD`; must add another method first | §10 |
| 9 | Apple / additional provider | N/A | New `user_identities` rows; Apple caveats: email revealed only on first auth (store `email_at_link`), private-relay emails make email matching useless → subject-only (L1/L3/L4; L2 rarely applicable) | §5 |
| 10 | Account deletion | Users row deletion semantics per existing product decisions | Identity rows cascade-delete; sessions revoked; a later login with the same provider account creates a fresh empty user (no resurrection); audit keeps hashed subject | §12 |

---

**Acceptance mapping:** strategy defined (§4–§8), all ten scenarios documented (§15), security risks and fail-closed rules documented (§7–§8), no code/migration/config changes (documentation-only).
