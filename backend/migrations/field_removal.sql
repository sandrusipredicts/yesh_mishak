-- E02-02: adds moderation-aware soft-delete columns to fields.
--
-- Hard-deleting a field is not safe: games.field_id and field_reports.field_id
-- both reference fields(id) ON DELETE CASCADE, so a hard delete would
-- silently destroy game history and field reports. Soft removal keeps the
-- row (and every relationship to it) intact while excluding it from public
-- listings and new-game creation.
--
-- No backfill needed: null removed_at means "never removed" for every
-- existing row.
alter table public.fields
    add column if not exists removed_at timestamptz,
    add column if not exists removed_by uuid references users(id) on delete set null,
    add column if not exists removal_reason text
        check (removal_reason is null or removal_reason in (
            'field_does_not_exist',
            'duplicate_field',
            'private_field',
            'school_property',
            'wrong_location',
            'invalid_field',
            'safety_issue',
            'other'
        ));

create index if not exists idx_fields_removed_at on fields(removed_at);

-- Matches the exact predicate used by the public field-listing queries
-- (GET /fields), so the planner can serve them from a narrow partial index
-- instead of scanning every approved field.
create index if not exists idx_fields_public_active_spatial
    on fields(lat, lng)
    where removed_at is null
      and verified = true
      and approval_status = 'approved'
      and status = 'open';
