-- ISSUE-095: Add tokens_valid_after column for JWT revocation on logout.
-- When a user logs out, this timestamp is set to now(). Any JWT with iat < tokens_valid_after is rejected.
alter table users add column if not exists tokens_valid_after timestamptz;
