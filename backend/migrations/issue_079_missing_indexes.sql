-- ISSUE-079: Missing database indexes
-- Implements all indexes recommended by ISSUE-078 database indexing audit.
-- Safe to re-run (all statements are idempotent).
-- Run in Supabase SQL Editor as a single batch.

-- =============================================
-- P1: HIGH PRIORITY
-- Affect every user on every app load
-- =============================================

-- P1-1: Fields public listing + spatial composite
-- Supports: GET /fields (bounded and unbounded)
-- Queries: .eq("verified",T).eq("approval_status","approved").eq("status","open") + .gte/.lte on lat/lng
-- The 5-column index covers the 3-column equality case as a prefix,
-- so a separate (verified, approval_status, status) index is not needed.
create index if not exists idx_fields_public_listing_spatial
    on fields(verified, approval_status, status, lat, lng);

-- P1-2: Games status filter
-- Supports: GET /games/active, GET /games/upcoming, POST /games duplicate check,
--           POST /admin/reminders/scheduled-games/run, GET /admin/games
-- Queries: .in_("status", ["open","full"])
create index if not exists idx_games_status
    on games(status);

-- P1-3: Games field_id + status composite
-- Supports: GET /fields game payload fan-out, POST /games duplicate check
-- Queries: .in_("field_id",...).in_("status",...) and .eq("field_id",...).in_("status",...)
create index if not exists idx_games_field_id_status
    on games(field_id, status);

-- P1-4: Notifications user_id + created_at ordered
-- Supports: GET /notifications (every notification screen load)
-- Queries: .eq("user_id",...).order("created_at", desc=True)
create index if not exists idx_notifications_user_id_created_at
    on notifications(user_id, created_at desc);

-- P1-5: Notifications unread partial index
-- Supports: GET /notifications/unread-count (polled every 20s per active user),
--           PATCH /notifications/read-all
-- Queries: .eq("user_id",...).is_("read_at","null")
create index if not exists idx_notifications_user_unread
    on notifications(user_id)
    where read_at is null;

-- =============================================
-- P2: MODERATE PRIORITY
-- Affect admin or lower-frequency paths
-- =============================================

-- P2-1: Fields approval status
-- Supports: GET /admin/fields/pending
-- Queries: .eq("approval_status","pending").order("created_at")
create index if not exists idx_fields_approval_status
    on fields(approval_status);

-- P2-2: Users last_login for monitoring
-- Supports: GET /admin/monitoring (DAU/WAU counts)
-- Queries: .gte("last_login", day_ago), .gte("last_login", week_ago)
create index if not exists idx_users_last_login
    on users(last_login);

-- P2-3: Notifications type + game_id for dedup checks
-- Supports: create_game_created_notifications, create_game_closed_notifications,
--           create_game_extended_notifications, generate_scheduled_game_reminders
-- Queries: .eq("type",...).eq("game_id",...).in_("user_id",...)
create index if not exists idx_notifications_type_game_id
    on notifications(type, game_id);

-- =============================================
-- P3: LOW PRIORITY
-- Nice to have for specific low-frequency paths
-- =============================================

-- P3-1: Push tokens user_id + token composite
-- Supports: DELETE /notifications/push-token
-- Queries: .delete().eq("user_id",...).eq("token",...)
create index if not exists idx_push_tokens_user_id_token
    on push_tokens(user_id, token);

-- P3-2: Notification preferences user_id + notification_type composite
-- Supports: PUT /notifications/preferences dedup check
-- Queries: .eq("user_id",...).eq("notification_type",...).eq("sport_type",...)
create index if not exists idx_notification_preferences_user_id_type
    on notification_preferences(user_id, notification_type);

-- =============================================
-- CLEANUP: Drop redundant indexes
-- =============================================

-- idx_notification_preferences_enabled: boolean column where most rows are true.
-- PostgreSQL query planner will never choose this index for .eq("enabled", True)
-- because selectivity is too low. No query uses .eq("enabled", False).
-- Confirmed useless in ISSUE-078 section 4.2.
drop index if exists idx_notification_preferences_enabled;
