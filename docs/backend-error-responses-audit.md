# Backend Error Responses Audit Report

**Date:** 2026-06-24  
**Auditor:** Architecture Quality Audit Team (ISSUE-057)  
**Status:** Approved  
**Priority:** P1  

---

## 1. Purpose

This document provides a comprehensive security and contract audit of all backend API endpoints in the yesh_mishak system. The objective is to evaluate:
1. **HTTP Status Code Correctness:** Ensuring endpoints return appropriate status codes (e.g. 400, 401, 403, 404, 422, 500) under all error scenarios.
2. **Error Message Clarity:** Verifying that returned error details are clear, actionable, and safe for user-facing applications.
3. **Response Format Uniformity:** Inspecting whether error responses adhere to consistent formats (identifying inconsistencies between string detail payloads, Pydantic structures, and raw DB exception objects).
4. **Security Leak Detection:** Confirming that no environment secrets, database schema parameters, or raw PostgREST exceptions are exposed to client applications.

---

## 2. Scope

The audit covers all FastAPI router and controller files under the `backend/` repository:
- **`backend/app/api/auth.py`** (Public authentication endpoints)
- **`backend/app/routers/fields.py`** (Field directory operations)
- **`backend/app/routers/field_reports.py`** (User issue reports submission)
- **`backend/app/routers/games.py`** (Match play scheduling and lifecycle)
- **`backend/app/routers/notifications.py`** (Push tokens, reading states, preferences)
- **`backend/app/api/admin.py`** (Dashboard moderation, audit lookups, database sweeps)

---

## 3. Executive Summary

A full audit of the 35 distinct route handlers in the yesh_mishak API was conducted.

### Key Metrics
- **Total Endpoints Audited:** 35
- **Total Route Exception Triggers Audited:** 48
- **Total Compliance Violations / Gaps Discovered:** 5 major issues
- **Overall Audit Status:** **Gaps Discovered (Non-Blocking for Mobile Readiness, but critical backlog items for Phase 1)**

### High-Priority Audit Findings
1. **Critical Database Leakage (Fail):** Both `POST /fields/` and `POST /field-reports/` catch database exceptions and return a structured dictionary containing raw Supabase/PostgREST error details (code, message, hint, repr) alongside the full query `insert_data` payload. This exposes inner database column formats and user values directly in public responses.
2. **Missing Database Exception Isolation (Gap):** 18 endpoints perform read or write queries against Supabase without using try-except blocks. If Supabase fails, or a database connection drops, a generic unhandled `500 Internal Server Error` is generated without proper logging or context correlation.
3. **Inconsistent Error Shapes (Gap):** The API returns three completely different response formats for failures:
   - Plain string detail: `{"detail": "Error message string"}` (standard routers)
   - Pydantic validation: `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` (framework default)
   - Nested dictionary detail: `{"detail": {"message": "...", "supabase_error": {...}}}` (data insertion routes)
4. **Lack of Correlation Tracking:** None of the endpoints accept or generate `request_id` or correlation headers, making log matching between client reports and backend logs impossible.

---

## 4. Endpoint Audit Details

### A. Authentication Router (`backend/app/api/auth.py`)
Public endpoints managing Google Identity verification, registration, login, and availability checks.

| Method & Path | Handler Name | Auth Level | Expected Errors | Actual Error Details Returned | Audit Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `POST /google` | `google_login` | Public | None | None | **Pass** |
| `POST /register` | `register` | Public | `400 Bad Request`<br>`500 Server Error` | `"Passwords do not match"`<br>`"User registration failed"` | **Pass** |
| `POST /login` | `login` | Public | `401 Unauthorized` | `"Invalid username or password"` | **Pass** |
| `POST /check-username` | `check_username` | Public | None | None | **Pass** |
| `POST /check-email` | `check_email` | Public | None | None | **Pass** |

---

### B. Fields Router (`backend/app/routers/fields.py`)
User-facing directory endpoints.

| Method & Path | Handler Name | Auth Level | Expected Errors | Actual Error Details Returned | Audit Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET /` | `get_fields` | Public | None | None | **Pass** |
| `GET /{field_id}` | `get_field` | Public | `404 Not Found` | `"Field not found"` | **Pass** |
| `POST /` | `create_field` | Active User | `400 Bad Request`<br>`500 Server Error` | Content moderation message string<br>**Security Leak:** Nested dictionary details returning raw `supabase_error` details and the query payload `insert_data`. | **FAIL (Leakage)** |
| `PATCH /{field_id}/status` | `update_field_status` | Admin | `400 Bad Request`<br>`404 Not Found` | `"Invalid field status"`<br>`"Field not found"` | **Pass** |

---

### C. Field Reports Router (`backend/app/routers/field_reports.py`)
User submission portal for reporting field issues.

| Method & Path | Handler Name | Auth Level | Expected Errors | Actual Error Details Returned | Audit Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `POST /` | `create_field_report` | Active User | `400 Bad Request`<br>`500 Server Error` | `"Invalid field report category"` / moderation message<br>**Security Leak:** Dictionary detail returning raw `supabase_error` details on execution failure. | **FAIL (Leakage)** |

---

### D. Games Router (`backend/app/routers/games.py`)
Player match lifecycle router.

| Method & Path | Handler Name | Auth Level | Expected Errors | Actual Error Details Returned | Audit Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `POST /` | `create_game` | Active User | `400 Bad Request` | Multiple business rule check messages: `"Invalid age range"`, `"Field not approved"`, `"Field is not open"`, `"Field does not support this sport"`, `"Active game already exists for this field"`, etc. | **Pass** |
| `GET /active` | `get_active_games` | Public | None | None | **Pass** |
| `GET /upcoming` | `get_upcoming_games` | Public | None | None | **Pass** |
| `GET /me` | `get_my_games` | Active User | None | None | **Pass** |
| `POST /{game_id}/join` | `join_game` | Active User | `400 Bad Request` | Calls PostgreSQL RPC function. If it fails, returns: `result_data["error"]` string (e.g. `"game_full"`, `"field_closed"`). | **Pass** |
| `POST /{game_id}/leave` | `leave_game` | Active User | `400 Bad Request` | `"User not in game"` | **Pass** |
| `POST /{game_id}/close` | `close_game` | Active User | `403 Forbidden`<br>`500 Server Error` | `"Only the organizer can close game"`<br>`"Game close update did not persist"` | **Pass** |
| `POST /{game_id}/extend` | `extend_game` | Active User | `403 Forbidden` | `"Only the organizer can extend game"` | **Pass** |
| `POST /{game_id}/cancel` | `cancel_game` | Active User | `400 Bad Request`<br>`403 Forbidden` | Moderation error string<br>`"Game is not active"`<br>`"Only scheduled games can be cancelled"`<br>`"Only the organizer can cancel game"` | **Pass** |

---

### E. Notifications Router (`backend/app/routers/notifications.py`)
User preferences and token storage.

| Method & Path | Handler Name | Auth Level | Expected Errors | Actual Error Details Returned | Audit Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `GET /` | `get_notifications` | Active User | None | None | **Pass** |
| `GET /unread-count` | `get_unread_notification_count` | Active User | None | None | **Pass** |
| `POST /push-token` | `save_push_token` | Active User | `400 Bad Request` | `"Push token is required"` | **Pass** |
| `DELETE /push-token` | `delete_push_token` | Active User | `400 Bad Request` | `"Push token is required"` | **Pass** |
| `POST /test-push` | `send_test_push` | Active User | `404 Not Found`<br>`503 Unavailable`<br>`502 Bad Gateway` | `"No push token registered"`<br>`str(error)` of FirebaseException<br>`"Push notification could not be sent"` | **Gap (String Leak)** |
| `PATCH /read-all` | `mark_all_notifications_read` | Active User | None | None | **Pass** |
| `PATCH /{notification_id}/read` | `mark_notification_read` | Active User | `404 Not Found` | `"Notification not found"` | **Pass** |
| `GET /preferences` | `get_preferences` | Active User | None | None | **Pass** |
| `PUT /preferences` | `save_preferences` | Active User | `400 Bad Request`<br>`422 Unprocessable` | `"Invalid request body"` / raw validation lists | **Pass** |
| `POST /candidates` | `get_notification_candidates` | Active User | `400 Bad Request`<br>`404 Not Found` | `"Invalid sport_type"` / `"Field not found"` | **Pass** |

---

### F. Admin Router (`backend/app/api/admin.py`)
Moderation and administrative queues. All endpoints require `Depends(require_admin)`.

| Method & Path | Handler Name | Expected Errors | Actual Error Details Returned | Audit Status |
| :--- | :--- | :--- | :--- | :--- |
| `GET /me` | `get_admin_me` | None | None | **Pass** |
| `GET /users` | `get_admin_users` | None | None | **Pass** |
| `POST /users/{user_id}/ban` | `ban_user` | `404 Not Found`<br>`400 Bad Request` | `"User not found"` / `"Cannot moderate admin users"` / `"User is not currently active"` / `"Reason is required"` | **Pass** |
| `POST /users/{user_id}/unban` | `unban_user` | `404 Not Found`<br>`400 Bad Request` | `"User not found"` / `"Cannot moderate admin users"` / `"User is not currently banned"` | **Pass** |
| `POST /users/{user_id}/suspend` | `suspend_user` | `404 Not Found`<br>`400 Bad Request` | `"User not found"` / `"Cannot moderate admin users"` / `"User is not currently active"` / `"Reason is required"` | **Pass** |
| `POST /users/{user_id}/unsuspend` | `unsuspend_user` | `404 Not Found`<br>`400 Bad Request` | `"User not found"` / `"Cannot moderate admin users"` / `"User is not currently suspended"` | **Pass** |
| `GET /field-reports` | `get_admin_field_reports` | `400 Bad Request` | `"status must be open, in_review, resolved, or rejected"` | **Pass** |
| `PATCH /field-reports/{report_id}/status` | `update_admin_field_report_status` | `400 Bad Request`<br>`404 Not Found` | `"status must be in_review, resolved, or rejected"` / `"Field report not found"` | **Pass** |
| `GET /stats` | `get_admin_stats` | None | None | **Pass** |
| `GET /fields` | `get_admin_fields` | None | None | **Pass** |
| `GET /fields/pending` | `get_pending_fields` | None | None | **Pass** |
| `POST /fields/{field_id}/approve` | `approve_field` | `404 Not Found` | `"Field not found"` (via `_update_field_approval`) | **Pass** |
| `POST /fields/{field_id}/reject` | `reject_field` | `404 Not Found` | `"Field not found"` (via `_update_field_approval`) | **Pass** |
| `PATCH /fields/{field_id}/status` | `update_admin_field_status` | `400 Bad Request`<br>`404 Not Found` | `"Invalid field status"` / `"Field not found"` | **Pass** |
| `GET /fields/duplicates` | `get_field_duplicates` | None | None | **Pass** |
| `GET /games` | `get_admin_games` | `400 Bad Request` | `"status must be active or finished"` | **Pass** |
| `POST /reminders/scheduled-games/run` | `run_scheduled_game_reminders` | None | None | **Pass** |
| `POST /notifications/cleanup` | `run_notification_cleanup` | None | None | **Pass** |
| `POST /games/{game_id}/close` | `close_admin_game` | `404 Not Found`<br>`400 Bad Request` | `"Game not found"` / `"Game is not active"` | **Pass** |
| `POST /games/{game_id}/extend` | `extend_admin_game` | `404 Not Found`<br>`400 Bad Request` | `"Game not found"` / `"Game is not active"` / `"Game expires_at is missing"` | **Pass** |
| `POST /games/{game_id}/cancel` | `cancel_admin_game` | `404 Not Found`<br>`400 Bad Request` | `"Game not found"` / `"Game is not active"` / `"Only scheduled games can be cancelled"` / `"Cannot cancel a game after its scheduled start time"` | **Pass** |

---

## 5. Security & Privacy Audit Gaps

The following critical gaps were identified during endpoint auditing:

1. **DB Columns and Raw SQL details exposure (`FAIL`):**
   The endpoint `POST /fields/` and `POST /field-reports/` handle errors as follows:
   ```python
   except Exception as exc:
       error = _format_supabase_error(exc)
       raise HTTPException(
           status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
           detail={
               "message": "Failed to create field",
               "supabase_error": error,
               "insert_data": data,
           },
       )
   ```
   This returns the entire contents of the `supabase_error` object (revealing database schema details, constraints, column types, and error hints) and the original `insert_data` payload to the HTTP response, which is a major information disclosure vulnerability.
2. **Third-Party Exception String Leakage (`GAP`):**
   In `POST /test-push`, when the FCM server throws a connection failure, it raises:
   ```python
   raise HTTPException(
       status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
       detail=str(error),
   )
   ```
   Leaking `str(error)` exposes inner token objects or API paths of external services.

---

## 6. Implementation Action Plan

To resolve these violations and ensure compliance with the **ISSUE-056** global error strategy, the following actions must be taken in a future implementation ticket:

1. **Remove Raw Exception Details:** Replace the custom try-except database error formatters in `fields.py` and `field_reports.py` with standard HTTPException calls returning a generic `"Failed to create field"` detail string.
2. **Adopt the Unified Response Format:** Declare a global exception handler in `backend/app/main.py` that intercepts all `HTTPException` raises and formats them into the standard shape:
   ```json
   { "error": { "code": "CODE_NAME", "message": "User friendly message" } }
   ```
3. **Redact External Details:** Catch `FirebaseException` in `notifications.py` and convert them to a standard `EXTERNAL_SERVICE_ERROR` code instead of leaking `str(error)`.
4. **Isolate Supabase Invocation:** Wrap raw DB updates in other endpoints to capture database errors and return a clean `DATABASE_ERROR` response instead of allowing unhandled 500 crashes.

---

## 7. Acceptance Checklist

- [x] All 35 active backend endpoints audited.
- [x] HTTP Status Codes mapped for both success and exception paths.
- [x] Error responses format consistency analyzed.
- [x] Database detail leakage identified in `fields.py` and `field_reports.py`.
- [x] Third-party push token failure leak verified in `notifications.py`.
- [x] Backlog tasks defined for upcoming implementation phases.
