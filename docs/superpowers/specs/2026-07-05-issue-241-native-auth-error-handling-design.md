# ISSUE-241 Native Authentication Error Handling Design

## Scope

Add centralized, user-safe error handling to the existing native Google login
flow. Preserve successful authentication and secure session persistence. Do not
change backend APIs, iOS native configuration, push notifications, or unrelated
authentication flows.

## Error contract

`mapNativeAuthError(error)` returns:

```js
{
  kind,
  messageKey,
  severity,
  shouldClearSession,
}
```

| Scenario | Kind | Message key | Severity | Clear session |
| --- | --- | --- | --- | --- |
| User cancellation | `cancelled` | `auth.signInCancelled` | `info` | Yes |
| Network/no response/timeout | `network` | `auth.networkError` | `error` | Yes |
| HTTP 400/401/403 | `verification_failed` | `auth.verificationFailed` | `error` | Yes |
| HTTP 5xx | `server_temporary` | `auth.serverTemporaryError` | `error` | Yes |
| Google plugin/provider failure | `google_provider_failed` | `auth.googleSignInFailed` | `error` | Yes |
| Missing provider ID token | `verification_failed` | `auth.verificationFailed` | `error` | Yes |
| Unknown failure | `unexpected` | `auth.signInUnexpectedError` | `error` | Yes |

## Runtime flow

The native handler keeps its existing `try/catch/finally`. On success, it uses
the existing exchange and session persistence pipeline unchanged. On failure,
it maps the error, defensively clears secure and legacy session state, renders
the translated message with informational or error semantics, and always
resets loading in `finally`.

The provider adapter gives missing-ID-token failures a stable non-sensitive
error code. Technical diagnostics may log safe classification metadata but
must never log credentials, response bodies, or complete error objects that
could contain tokens.

## Testing

Focused tests cover every mapper branch and native UI behavior: cancellation,
network failure, verification failure, server failure, provider failure,
missing ID token, unknown fallback, defensive cleanup, button re-enablement,
and unchanged successful persistence. Full lint, test, and frontend builds run
after the focused suite passes.

## Completion boundary

Automated completion of this implementation does not make ISSUE-241 fully
done. Native iPhone validation remains pending because ISSUE-240 is not yet
validated on iPhone.
