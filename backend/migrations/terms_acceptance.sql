-- E10-08: record non-skippable Terms of Service acceptance for UGC access.
-- Existing accounts must accept on their next fresh authentication.

alter table public.users
    add column if not exists terms_accepted_at timestamptz;
