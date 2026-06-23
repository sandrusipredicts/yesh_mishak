# Global Error Handling Strategy

**Date:** 2026-06-24  
**Author:** Architecture Team (ISSUE-056)  
**Status:** Approved  
**Priority:** P0  

---

## 1. Purpose

Before transitioning the yesh_mishak platform into Mobile Readiness (EPIC 02), the system must have a unified, predictable, and robust contract for managing and communicating errors. 

A global error handling strategy is critical because:
- **Mobile Network Vulnerability:** Mobile clients operate in high-latency, offline, or unstable network environments. They require specific guidance on when to retry operations and how to cache requests.
- **Client-Backend Decoupling:** Mobile apps cannot rely on parsing English error strings from the backend. They must read standardized, machine-readable error codes to dynamically render localized error messages.
- **Security & Leak Prevention:** Unhandled database errors or raw API tracebacks leak internal schema definitions and environment metadata.
- **Developer Consistency:** Provides a single contract so that backend and frontend developers handle exceptions, logging, and user feedback uniformly.

---

## 2. Scope

This strategy covers all components and operational boundaries in the yesh_mishak system:
- **Backend API Layer:** FastAPI routers, middlewares, and authorization dependencies.
- **Data Access Layer:** Supabase client queries, transaction failures, and Row-Level Security (RLS) violations.
- **Frontend App:** React SPA (Vite + Axios), interceptors, and page/component-level catch handlers.
- **Mobile Clients (Future):** Flutter/native clients, state managers, and API drivers.
- **External Integration Points:** Firebase Cloud Messaging (FCM) push tokens, Google OAuth token verification, and Map/Geocoding services.
- **Operational Scripts:** Database migrations, audits, and GovMap facility import scripts.

---

## 3. Non-Goals

To keep the scope of ISSUE-056 tightly focused, the following boundaries are defined:
- **No Immediate Code Changes:** This issue does not implement new Python error classes, FastAPI middlewares, or Axios interceptors. It is a strategic architectural specification only.
- **No Endpoints Refactoring:** Existing backend endpoints or frontend pages will not be altered or refactored in this ticket.
- **No Database Migrations:** No schema modifications or database changes will be introduced.
- **No Frontend UI Refactoring:** No current UI forms or modal warning states will be redesigned.
- **No Leakage of Stack Traces:** Internal technical details will remain masked from public endpoints under all circumstances.

---

## 4. Error Response Contract

The system will move from its current inconsistent error formats to a single, unified backend API error response payload.

### Target API Error Shape
All error responses (HTTP status codes >= 400) must return the following JSON payload shape:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The field coordinates are invalid or out of bounds.",
    "details": {
      "lat": "Value must be between 29.5 and 33.5"
    },
    "request_id": "req-8f92b71c-f23a"
  }
}
```

### Contract Fields Definition
- **`code` (string, required):** A uppercase, snake_case canonical error code (e.g. `GAME_FULL`, `FORBIDDEN`) mapping to the [Error Code Catalog](#15-error-code-catalog). This is the key the frontend/mobile client uses for logic and translation mapping.
- **`message` (string, required):** A safe, user-friendly, and localized (where possible) message explaining what went wrong. Safe for direct display in toast notifications or error labels.
- **`details` (object/list, optional):** Structured metadata explaining specific validation failures (e.g. input field names and their specific violations).
- **`request_id` (string, optional):** A unique correlation ID generated at the gateway/middleware layer to trace requests in server-side logs.

### Current Shape vs. Target Shape Comparison
Currently, the backend exhibits three different shapes:
1. **FastAPI HTTPExceptions:** `{"detail": "Error message string"}`
2. **Pydantic Validation Errors:** `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`
3. **Database Exceptions (e.g. `fields.py`):** Returns a custom dictionary containing raw database details:
   ```json
   {
     "detail": {
       "message": "Failed to create field",
       "supabase_error": { "type": "PostgrestAPIError", "message": "..." },
       "insert_data": { ... }
     }
   }
   ```

### Migration Requirement
During the implementation phase, a FastAPI Exception Handler must capture both `HTTPException` and `RequestValidationError`, formatting them into the unified `{"error": ...}` target shape before sending them to the client. This ensures backwards compatibility for routes not yet refactored.

---

## 5. Backend Error Taxonomy

To organize backend failures, the system defines nine distinct error categories:

### A. Validation Errors
- **HTTP Status:** `422 Unprocessable Entity` (FastAPI standard for input schema mismatches) or `400 Bad Request` (for logic-based validations, such as invalid coordinates).
- **Examples:** Empty required name, out-of-bounds latitude/longitude, invalid report category, or offensive language flagged by moderation.
- **Client Behavior:** Show inline validation errors next to the form field. Do not retry automatically.

### B. Authentication Errors
- **HTTP Status:** `401 Unauthorized`
- **Examples:** Missing HTTP Bearer header, expired JWT token, invalid credentials, or Google Identity verification failure.
- **Client Behavior:** Wipe local session state, redirect user to the login screen, or attempt token refresh. Do not display standard server failure popups.

### C. Authorization Errors
- **HTTP Status:** `403 Forbidden`
- **Examples:** Regular user attempting to access `/admin/*` routes, a participant trying to cancel a game they did not create, or a banned/suspended user making API requests.
- **Client Behavior:** Display a "Permission Denied" warning. Do not retry.

### D. Not Found Errors
- **HTTP Status:** `404 Not Found`
- **Examples:** Requested `field_id` or `game_id` does not exist in the database.
- **Client Behavior:** Display a "Not Found" state, redirect user to home, or trigger a list refresh.

### E. Conflict / Business Rule Errors
- **HTTP Status:** `409 Conflict` (preferred for state mismatches) or `400 Bad Request`.
- **Examples:** Player attempting to join a game that is already `full`, joining a game on a `closed` field, or cancelling a game that has already started.
- **Client Behavior:** Show a specific, descriptive popup (e.g. "This game is already full"), refresh the local UI state, and do not auto-retry.

### F. Database Errors
- **HTTP Status:** `500 Internal Server Error`
- **Examples:** PostgreSQL constraint violation, database timeout, network drop between FastAPI and Supabase, or RLS permission failure.
- **Client Behavior:** Show a generic "Temporary Service Outage" alert. Retry only if the action is safe (idempotent GET queries).
- **Server Logging:** Log the full database exception, query parameters, and trace. Never expose PostgREST or PostgreSQL error details in the API response.

### G. External Service Errors
- **HTTP Status:** `502 Bad Gateway` or `503 Service Unavailable`
- **Examples:** Firebase Cloud Messaging (FCM) fails to send a push notification, or Google token authentication endpoint is down.
- **Client Behavior:** If the core action succeeds (e.g., game cancellation is written to DB) but a side effect fails (push notification fails to send), the API must catch the exception, log it, and return a successful `200 OK` response to the user with a logged warning.

### H. Rate Limit / Abuse Protection Errors
- **HTTP Status:** `429 Too Many Requests`
- **Examples:** IP rate limit exceeded, or user submitting multiple fields/reports within a short window.
- **Client Behavior:** Block request buttons, show a "Too many requests. Please wait X seconds" message.

### I. Unknown / Unhandled Errors
- **HTTP Status:** `500 Internal Server Error`
- **Examples:** Unhandled Python `KeyError`, `ValueError`, or index out of range.
- **Client Behavior:** Display a generic "Something went wrong" message.
- **Server Logging:** Must log the traceback along with the route context, request body, and user ID.

---

## 6. HTTP Status Code Map

| Error Category | HTTP Status | Code Example | Auto-Retry? | User-Facing UI Message Type | Log Severity |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Validation** | `422` or `400` | `VALIDATION_ERROR` | No | Form field input error | Info |
| **Authentication** | `401` | `AUTH_REQUIRED` | No (Redirect) | Login redirect / screen prompt | Info |
| **Authorization** | `403` | `FORBIDDEN` | No | "Access Denied" blocker page | Warning |
| **Not Found** | `404` | `NOT_FOUND` | No | "Resource not found" page/toast | Info |
| **Conflict / Business Rule** | `409` | `GAME_FULL` | No | Toast notification / popup banner | Warning |
| **Database** | `500` | `DATABASE_ERROR` | Idempotent only | Generic "Server outage" toast | Error |
| **External Service** | `502` / `503` | `EXTERNAL_SERVICE_ERROR` | Yes (Delayed) | Generic "Notifications delayed" banner | Warning |
| **Rate Limit** | `429` | `RATE_LIMITED` | Yes (Cool-down) | Cooldown timer message | Warning |
| **Unknown** | `500` | `UNKNOWN_ERROR` | No | Generic "Contact support" popup | Error / Critical |

---

## 7. Backend Handling Rules

To prevent error leakage and maintain API contract stability, developers must follow these backend rules:
1. **Raise Early, Handle Late:** Raise descriptive domain exceptions inside routers/services when business logic fails. Let them bubble up to a centralized Exception Handler middleware rather than wrapping every DB call in inline try-except blocks.
2. **Sanitize Database Exceptions:** Do not leak database structures. Catch all Supabase/PostgREST exceptions at the router/middleware level and convert them into a generic `DATABASE_ERROR` code.
3. **Handle Best-Effort Side Effects:** Side effects (like notifications or background tasks) must not fail the primary request. Wrap notification generation in try-except blocks:
   ```python
   try:
       create_notifications()
   except Exception:
       logger.exception("Notification dispatch failed") # Log as warning, but return 200 OK
   ```
4. **Stable API Contracts:** Never change the schema of the `{"error": ...}` response. If new error codes are added, they must be appended to the global catalog without modifying the structure of the `details` object.

---

## 8. Frontend Error Handling Strategy

Frontend applications (React SPA and future Mobile apps) must handle network and service failures gracefully.

### A. Network Failure
- **Definition:** The user has no internet access, DNS lookup fails, or API is completely unreachable.
- **User Message:** "No internet connection. Please check your network and try again."
- **Retry Behavior:** Show a retry button or retry automatically using exponential backoff (e.g. 3 attempts).
- **UI Behavior:** Show an offline banner or a full-page offline state. Disable form submit buttons.
- **Mobile Implication:** Cache data locally. Enqueue write actions (like reports) to sync once network restores.

### B. API Failure
- **Definition:** The API responded with a non-2xx status code and a structured error payload.
- **User Message:** Use the code in the response to show a translated localized message (e.g. `t('errors.' + error.code)`).
- **Retry Behavior:** Do not retry if the error is a `4xx` validation, authorization, or business conflict.
- **UI Behavior:** Render form highlights (422) or show popup/toast notifications (409/404).

### C. Timeout
- **Definition:** The network connection takes longer than the maximum timeout limit (default: 10 seconds).
- **User Message:** "The connection timed out. Please try again."
- **Retry Behavior:** Allow the user to retry manually. 
- **UI Behavior:** Display a "Connection Slow" warning.
- **Mobile Implication:** Highly critical on mobile where cell reception fluctuates.

### D. Unknown Error
- **Definition:** Browser crash, JS rendering exception, or unexpected JSON parsing error.
- **User Message:** "An unexpected error occurred. Please refresh the page."
- **Retry Behavior:** Allow refreshing the page.
- **Logging:** Log diagnostic details to an internal console or tracking system (like Sentry).

---

## 9. Frontend UX Rules

1. **Context-Specific Placement:** Show validation errors immediately adjacent to the form fields (red outline, helper text). Do not dump validation lists into generic alert banners.
2. **Auth Interception:** Global interceptors must intercept `401 Unauthorized` responses and immediately redirect to login.
3. **Submit Button Safeguards:** Disable submit buttons immediately upon click and display a loading/spinner state. This prevents users from clicking multiple times and generating duplicate API requests.
4. **Destructive Actions Guard:** For destructive or state-changing actions (e.g. cancelling a game or leaving a game), do not auto-retry on timeout or network drops without first checking the resource status. This avoids duplicate cancellations or joins.
5. **Mask Technical Terms:** Never show backend terms like "Supabase", "database constraint", or "PostgrestAPIError" in the UI.

---

## 10. Mobile Readiness Implications

Developing mobile applications introduces several considerations that depend on this strategy:
- **Offline Mode Integration:** Mobile clients must check network connectivity before making API calls. They must use SQLite/Hive to store local settings and cache data.
- **Strict Code-to-Translation Mapping:** Since mobile clients are distributed via App Stores, they cannot be updated instantly when backend text changes. Localizing error messages requires mapping stable error codes (`VALIDATION_ERROR`, `GAME_FULL`) to in-app translations.
- **Idempotency on State Changes:** Mobile applications must handle flaky connections by checking if the action has already occurred (e.g., fetching user games first) before retrying a timeout-failed `/games/{id}/join` request.

---

## 11. Logging and Observability

1. **Server-Side Log Integrity:** Server logs must capture the full traceback, request path, HTTP method, user ID, and `request_id`.
2. **Secrets Redaction:** Log filters must scrub parameters like `password`, `access_token`, `authorization`, and `credential` before writing to standard output.
3. **Log Severities:**
   - `CRITICAL`: System-wide failures (e.g., Supabase completely unreachable).
   - `ERROR`: Unhandled exceptions and database write failures.
   - `WARNING`: Handled business violations (e.g., banned user attempts access, notification failure).
   - `INFO`: Normal router execution flow.
4. **Correlation:** A unique `request_id` should be included in the server log statement and returned in the HTTP headers (`X-Request-ID`) to simplify support triage.

---

## 12. Security and Privacy Rules

- **Hide Stack Traces:** Under no circumstances should the backend return stack traces or raw code representations (like Python traceback strings) to the client.
- **Safe Authentication Errors:** When authentication fails, return a generic error message (e.g. "Invalid username or password") rather than exposing whether the user ID exists or the email was correct.
- **Contain DB Error Fields:** Database error mappings must not echo back the query input payload if it contains personal identifier details.
- **Sanitize Moderation Errors:** When content is rejected by moderation, do not echo the prohibited text back in the error message. Provide a safe confirmation instead (e.g. "Content violates community guidelines").

---

## 13. Current Gaps / Implementation Backlog

During the codebase audit, the following architectural gaps were identified:
1. **Raw Database Errors Leaked in `fields.py`:**
   - *Code Reference:* `backend/app/routers/fields.py#L152-L163`
   - *Issue:* The `except Exception as exc` block format returns the raw `supabase_error` details and `insert_data` payload directly to the client API response, exposing inner tables and data variables.
2. **No Centralized Exception Handling:**
   - *Code Reference:* `backend/app/main.py`
   - *Issue:* FastAPI's main instance does not declare global handlers for `RequestValidationError` or general `Exception` types.
3. **Leaked Supabase Failures in Routers:**
   - *Code Reference:* `backend/app/routers/games.py`, `backend/app/routers/field_reports.py`
   - *Issue:* Database `.execute()` commands are called directly without try-except blocks. If Supabase fails, it returns unhandled HTTP 500 errors to the client.
4. **Scattered Client Interceptors & Empty Catch Blocks:**
   - *Code Reference:* `frontend/src/api/client.js`, `AddFieldModal.jsx#L122`
   - *Issue:* No Axios response interceptors exist to handle general errors or redirect on 401s. Components implement custom `catch (apiError)` logic with generic fallbacks.
5. **Absence of Request IDs:**
   - *Code Reference:* `backend/app/main.py`
   - *Issue:* The backend lacks a middleware to inject `request_id` or correlation headers.

---

## 14. Recommended Implementation Phases

### Phase 1: Backend Scaffolding & Normalization (Immediate)
- Implement a global exception handler in `main.py` to capture `HTTPException` and `RequestValidationError`.
- Format all error responses into the structured `{"error": ...}` target shape.
- Remove raw Supabase details in `fields.py` and wrap database execution in games/reports routers.
- Introduce the canonical error code catalog into a backend constants module.

### Phase 2: Frontend Interceptor & Unified UI Triggers (Mid-term)
- Configure an Axios response interceptor in `client.js` to catch errors globally.
- Redirect users to login on `401 Unauthorized` responses.
- Create a shared frontend utility to parse backend error codes and map them to localization keys (`i18n`).
- Implement button-disabling states across all submission forms to prevent double clicks.

### Phase 3: Correlation & Distributed Observability (Long-term)
- Add a FastAPI middleware to generate a unique `request_id` for every request.
- Attach the `X-Request-ID` header to all API responses.
- Include `request_id` in all server logs.
- Integrate structured log formats (JSON) suitable for log aggregators (e.g. Sentry, Grafana, Datadog).

---

## 15. Error Code Catalog

| Error Code | Category | HTTP Status | Description | Safe Frontend Message |
| :--- | :--- | :--- | :--- | :--- |
| `VALIDATION_ERROR` | Validation | `422` or `400` | Input data fails validation rules (missing fields, format errors). | "Please check your inputs and try again." |
| `AUTH_REQUIRED` | Authentication | `401` | Session is missing or invalid. Authentication required. | "Please sign in to continue." |
| `AUTH_INVALID` | Authentication | `401` | Credential verification or Google OAuth login failed. | "Invalid username or password." |
| `FORBIDDEN` | Authorization | `403` | User does not have sufficient role or permission. | "You do not have permission to perform this action." |
| `ACCOUNT_RESTRICTED`| Authorization | `403` | User account is banned or suspended. | "This account has been restricted by administrators." |
| `NOT_FOUND` | Not Found | `404` | The requested resource (field, game, report) does not exist. | "The requested item was not found." |
| `CONFLICT` | Conflict | `409` | The action conflicts with the current resource state. | "State conflict occurred. Please refresh." |
| `FIELD_NOT_OPEN` | Conflict | `400` | Game creation/join attempted on a closed or renovation field. | "This field is not currently open for play." |
| `GAME_FULL` | Conflict | `409` | Player limit has been reached. | "This game is already full." |
| `GAME_NOT_ACTIONABLE`| Conflict | `400` | Actions attempted on finished or expired games. | "This game is no longer active." |
| `CONTENT_REJECTED` | Validation | `400` | Content fails community moderation checks (profanity, PII). | "Content violates community guidelines." |
| `RATE_LIMITED` | Rate Limit | `429` | User is making too many requests. | "Too many requests. Please wait a moment." |
| `DATABASE_ERROR` | Database | `500` | Internal database read/write transaction failed. | "A temporary server error occurred. Please try again." |
| `EXTERNAL_ERROR` | External | `502` / `503` | Integration with third-party service (FCM, maps) failed. | "External service is temporarily unavailable." |
| `TIMEOUT` | Network | `504` | Request timed out before completion. | "The connection timed out. Please try again." |
| `UNKNOWN_ERROR` | Unknown | `500` | An unhandled system-level failure occurred. | "Something went wrong. Please contact support." |

---

## 16. Acceptance Checklist

- [x] Backend validation errors defined with status codes and example scenarios.
- [x] Backend auth errors defined with JWT/Google Identity failures.
- [x] Backend authorization errors defined for restricted roles and status blocks.
- [x] Backend database errors defined, covering Supabase and RLS violations.
- [x] Backend external service errors defined (FCM push, OAuth endpoints).
- [x] Frontend network failure defined, covering online/offline states.
- [x] Frontend API failure defined with error parsing rules.
- [x] Frontend timeout defined with retry expectations.
- [x] Frontend unknown error defined with logging recommendations.
- [x] Mobile readiness implications defined, emphasizing offline states and stable contracts.
- [x] Security and privacy rules defined (sanitization, no secrets leakage).
- [x] Implementation backlog defined using codebase audit findings.
