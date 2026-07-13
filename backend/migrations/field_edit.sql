-- E02-01: adds an updated_at timestamp so admin field edits (PATCH
-- /admin/fields/{field_id}) can record when a field was last changed.
-- No backfill needed: null means "never edited since this column existed".
alter table public.fields
    add column if not exists updated_at timestamptz;
