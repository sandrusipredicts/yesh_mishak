# Google identity linking and login

## Identity model

`users.id` is the application identity used by profiles, games, notifications,
administration, and ownership relationships. `user_identities` stores external
authentication identities. Google is keyed by `(provider = 'google',
provider_subject = Google sub)` and only one Google identity is allowed per
application user. `users.google_sub` remains a compatibility mirror and is not
the login lookup source of truth.

The backend verifies every Google ID token against `GOOGLE_CLIENT_ID`, requires
`email_verified = true`, and reads `sub` and email only from verified claims.
Identity reads and mutations use service-role-only database functions; Google
tokens are never sent to Supabase or written to logs.

## Authentication flows

1. Email/password registration normalizes the email, creates one `users` row
   with a password hash, and starts email verification. It creates no provider
   identity.
2. Email/password login resolves username or normalized email, verifies the
   password and email-verification state, and issues an application JWT whose
   subject is the existing `users.id`.
3. Google login verifies the token, resolves `user_identities` by Google `sub`,
   and returns the linked `users.id`. If neither identity nor email exists, the
   database creates one user and one identity in a single transaction.
4. If Google login has no subject mapping but its verified email already belongs
   to an application user, it returns `409 ACCOUNT_LINK_REQUIRED`. Email alone
   never links or merges accounts. A legacy `users.google_sub` match may be
   backfilled because it is a stable-subject match.
5. Settings linking requires an application JWT and calls
   `POST /auth/link/google`. The verified subject is linked to the authenticated
   `users.id`; no user is created. Repeating the same subject is idempotent. A
   different subject already owned by either side, or a provider email owned by
   another user, returns `409` without mutation.
6. After linking, `POST /auth/google` resolves the new identity row and issues a
   JWT with the original application user ID. Password login remains unchanged.
7. `POST /auth/unlink/google` requires the current password and refuses to
   remove the last usable sign-in method. It deletes only the identity mapping
   and compatibility mirror, never the application user.

## Transaction and migration safety

`migrations/google_identity_resolution.sql` locks the affected tables while it
audits legacy data. It stops rather than deleting or ignoring duplicate
provider subjects, multiple identities for one provider/user, case-insensitive
duplicate user emails, blank identities, or mismatched legacy subjects.

Google login creation and Settings linking use advisory transaction locks plus
the existing unique constraints. User creation and identity creation occur in
one database function/subtransaction. A uniqueness race is re-resolved to the
winning identity or to `ACCOUNT_LINK_REQUIRED`; it cannot leave an orphan user.

Linking is additive and does not advance `tokens_valid_after`, so the session
that authorized the link remains valid. Unlinking and password mutations retain
the existing session-revocation behavior.

## Production migration runbook

Do not deploy the backend that calls `resolve_google_login` before the database
migration. Do not replay every file in `backend/migrations` alphabetically; the
repository predates ordered migration filenames. On an existing production
database where the account-linking and token-revocation migrations are already
installed, execute only `google_identity_resolution.sql`.

### 1. Backup and recovery prerequisite

Before the maintenance window:

1. Confirm a current Supabase backup or PITR restore point and confirm that the
   operator knows which project and timestamp would be restored.
2. Take a logical backup and verify that PostgreSQL can read its catalog:

   ```sh
   pg_dump "$DATABASE_URL" --format=custom --file=google-identity-predeploy.dump
   pg_restore --list google-identity-predeploy.dump > google-identity-predeploy.list
   ```

3. Save the currently deployed Settings-link function. This is the function-only
   rollback artifact:

   ```sh
   psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 -Atc \
     "select pg_get_functiondef('public.link_google_identity(uuid,text,text)'::regprocedure)" \
     > link_google_identity.predeploy.sql
   ```

Do not continue if the backup is missing, the catalog cannot be read, the saved
function is empty, or a restore owner has not been identified.

### 2. Read-only schema and privilege preflight

Run this against the production project before pausing traffic. It returns no
`missing_column` or `missing_constraint` rows on the currently supported
schema.

```sql
begin read only;

select current_database() as database_name, current_user as migration_role;

with required(table_name, column_name) as (
    values
        ('users', 'id'),
        ('users', 'google_sub'),
        ('users', 'email'),
        ('users', 'name'),
        ('users', 'picture'),
        ('users', 'email_verified'),
        ('users', 'email_verified_at'),
        ('user_identities', 'user_id'),
        ('user_identities', 'provider'),
        ('user_identities', 'provider_subject'),
        ('user_identities', 'email_at_link'),
        ('user_identities', 'email_verified_at_link'),
        ('user_identities', 'last_used_at')
)
select r.table_name, r.column_name as missing_column
from required r
left join information_schema.columns c
  on c.table_schema = 'public'
 and c.table_name = r.table_name
 and c.column_name = r.column_name
where c.column_name is null;

with required(table_name, definition) as (
    values
        ('users', 'PRIMARY KEY (id)'),
        ('users', 'UNIQUE (google_sub)'),
        ('users', 'UNIQUE (email)'),
        ('user_identities', 'UNIQUE (provider, provider_subject)'),
        ('user_identities', 'UNIQUE (user_id, provider)'),
        ('user_identities', 'FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE')
)
select r.table_name, r.definition as missing_constraint
from required r
where not exists (
    select 1
    from pg_constraint c
    where c.conrelid = ('public.' || r.table_name)::regclass
      and pg_get_constraintdef(c.oid) = r.definition
);

select column_default as users_id_default
from information_schema.columns
where table_schema = 'public' and table_name = 'users' and column_name = 'id';

select
    to_regprocedure('public.link_google_identity(uuid,text,text)') as link_rpc,
    to_regprocedure('public.unlink_google_identity(uuid)') as unlink_rpc,
    to_regprocedure('public.set_account_password(uuid,text)') as set_password_rpc,
    to_regprocedure('public.remove_account_password(uuid)') as remove_password_rpc;

select
    c.oid::regclass as object,
    pg_get_userbyid(c.relowner) as owner,
    has_table_privilege(current_user, c.oid, 'SELECT') as can_select,
    has_table_privilege(current_user, c.oid, 'INSERT') as can_insert,
    has_table_privilege(current_user, c.oid, 'UPDATE') as can_update,
    c.relrowsecurity as rls_enabled,
    c.relforcerowsecurity as rls_forced
from pg_class c
where c.oid in ('public.users'::regclass, 'public.user_identities'::regclass);

select
    p.oid::regprocedure as function,
    pg_get_userbyid(p.proowner) as owner
from pg_proc p
where p.oid = 'public.link_google_identity(uuid,text,text)'::regprocedure;

rollback;
```

Expected results:

- no missing columns or constraints;
- `users_id_default` contains `gen_random_uuid()`;
- all four existing account-mutation RPCs resolve;
- the migration role is the trusted owner, normally `postgres`, or otherwise
  owns the existing function and has the displayed table privileges plus the
  ability to lock both tables;
- forced RLS is off, or the trusted function owner has `BYPASSRLS`.

The migration also needs `CREATE` on `public`, authority to replace the existing
`link_google_identity` function, and authority to revoke/grant execution to the
Supabase `anon`, `authenticated`, and `service_role` roles. Run it from the
Supabase SQL Editor as the project owner or with an equivalent database-owner
connection. Never run it with an application or end-user credential.

### 3. Execution order

1. Schedule a short authentication maintenance window. Pause Google login and
   Settings-link writes. Reads may continue.
2. Confirm the backup, saved function, schema preflight, and production project
   identity.
3. Execute `backend/migrations/google_identity_resolution.sql` as one bounded
   transaction:

   ```sh
   psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 --single-transaction \
     -c "set local lock_timeout = '10s'; set local statement_timeout = '5min';" \
     -f backend/migrations/google_identity_resolution.sql
   ```

   In the Supabase SQL Editor, run the equivalent single batch:

   ```sql
   begin;
   set local lock_timeout = '10s';
   set local statement_timeout = '5min';
   -- Paste google_identity_resolution.sql here, unchanged.
   commit;
   ```

4. Expected `psql` command tags are `SET`, `SET`, `LOCK TABLE`, `DO`,
   `INSERT 0 N`, two `CREATE FUNCTION`, two `REVOKE`, two `GRANT`, and
   `COMMIT`. `N` is the count of unambiguous legacy identities backfilled and
   may be zero. Any `ERROR` means the transaction did not succeed; do not
   deploy the dependent backend.
5. Verify the committed database state:

   ```sql
   select
       to_regprocedure('public.resolve_google_login(text,text,text,text)') as resolver,
       to_regprocedure('public.link_google_identity(uuid,text,text)') as linker,
       has_function_privilege(
           'service_role',
           'public.resolve_google_login(text,text,text,text)',
           'EXECUTE'
       ) as service_role_can_resolve,
       has_function_privilege(
           'anon',
           'public.resolve_google_login(text,text,text,text)',
           'EXECUTE'
       ) as anon_can_resolve,
       has_function_privilege(
           'authenticated',
           'public.resolve_google_login(text,text,text,text)',
           'EXECUTE'
       ) as authenticated_can_resolve;

   select count(*) as legacy_rows_missing_identity
   from public.users u
   where u.google_sub is not null
     and not exists (
         select 1
         from public.user_identities ui
         where ui.user_id = u.id and ui.provider = 'google'
     );
   ```

   Both function names must resolve, the three privilege booleans must be
   `true`, `false`, `false`, and `legacy_rows_missing_identity` must be zero.
6. Deploy the backend, then the web frontend. Resume Google auth only after the
   backend health check and a controlled smoke test. Release Android through
   its normal signed-build process after web verification.

The migration uses `SHARE ROW EXCLUSIVE` locks on `users` and
`user_identities`. Ordinary `SELECT` statements continue, but inserts, updates,
deletes, and competing schema changes wait until commit. The `10s` lock timeout
prevents an indefinite wait; the lock is held for the preflight scans,
backfill, function replacement, and grants. Time the scans in staging against a
production-sized copy before choosing the maintenance window.

The script is retry-safe after a rolled-back attempt. After a successful run,
re-execution should report `INSERT 0 0` and replace the same functions and
grants. This is an operational idempotency property, not a substitute for a
migration ledger.

### 4. Explicit data-preflight failures

The migration deliberately raises exactly these six data errors. Save the query
results with the incident ticket before changing any row. Repairs must happen
in a separate reviewed transaction and must be based on stable Google `sub`
evidence or verified account ownership, never email similarity alone.

| Error | Diagnostic query | Safe repair |
| --- | --- | --- |
| `Duplicate (provider, provider_subject) rows require manual repair` | `select provider, provider_subject, count(*), array_agg(user_id) from public.user_identities group by provider, provider_subject having count(*) > 1;` | Identify the legitimate owner from provider-subject evidence. Quarantine/export the duplicate rows, remove only the adjudicated invalid mapping, and restore the unique constraint if schema drift allowed the duplicates. Do not merge application users automatically. |
| `Multiple identities for one user/provider require manual repair` | `select user_id, provider, count(*), array_agg(provider_subject) from public.user_identities group by user_id, provider having count(*) > 1;` | Confirm the currently valid subject with the provider/account owner, retain one mapping, archive and remove the obsolete mapping, then restore the `(user_id, provider)` unique constraint. |
| `Case-insensitive duplicate user emails require manual repair` | `select lower(btrim(email)) as normalized_email, count(*), array_agg(id) from public.users where email is not null group by lower(btrim(email)) having count(*) > 1;` | Do not auto-link or auto-merge. Verify both accounts, then either change one primary email or execute the application's separately reviewed account/data merge procedure. Re-run ownership and foreign-key checks afterward. |
| `Blank provider identity values require manual repair` | `select id, user_id, provider, provider_subject from public.user_identities where btrim(provider) = '' or btrim(provider_subject) = '';` | Recover the stable provider/subject from trusted provider evidence. If it cannot be recovered, archive the row and remove the unusable identity; never synthesize a subject from email. |
| `A legacy Google subject is mapped to another application user` | `select u.id as legacy_user_id, u.google_sub, ui.id as identity_id, ui.user_id as identity_user_id from public.users u join public.user_identities ui on ui.provider = 'google' and ui.provider_subject = u.google_sub and ui.user_id <> u.id where u.google_sub is not null;` | Establish which user owns the Google subject. Preserve the canonical identity mapping and clear/correct only the stale `users.google_sub` compatibility mirror, unless provider evidence proves the identity row itself is wrong. Do not move profiles or games based only on email. |
| `A user has conflicting legacy and canonical Google subjects` | `select u.id, u.google_sub as legacy_subject, ui.id as identity_id, ui.provider_subject as canonical_subject from public.users u join public.user_identities ui on ui.provider = 'google' and ui.user_id = u.id and ui.provider_subject <> u.google_sub where u.google_sub is not null;` | Verify the current Google `sub`. Normally retain the verified `user_identities` row and update the compatibility mirror to match; change the canonical row only with provider-subject evidence and after checking global uniqueness. |

After a repair, run all six diagnostic queries in one transaction. Continue only
when every query returns zero rows and the required uniqueness/FK constraints
are present.

### 5. Environmental failures and recovery

These errors occur before or around the deliberate data audit and are also
fail-closed:

| Error/signature | Safe response |
| --- | --- |
| `canceling statement due to lock timeout` | The transaction rolls back. Keep writes paused, inspect the blocking transaction in `pg_stat_activity`/`pg_locks`, let its owner finish or cancel it through the normal incident process, then retry. Do not blindly terminate sessions. |
| `canceling statement due to statement timeout` | The transaction rolls back. Measure the six scans and backfill on a production-sized staging copy, investigate missing indexes or abnormal volume, and approve a longer window before retrying. |
| `permission denied`, `must be owner of function`, or `permission denied for schema public` | Roll back and reconnect as the trusted project/database owner. Do not grant migration powers to the application role. |
| `relation ... does not exist`, `column ... does not exist`, missing UUID default, or a missing required constraint | The deployed schema is not at the supported baseline. Stop. Reconcile it against `backend/schema.sql` and the account-linking prerequisites in staging, then apply the separately reviewed prerequisite migration before retrying this migration. |
| `role "anon"`, `"authenticated"`, or `"service_role" does not exist` | Confirm that the connection targets the intended Supabase project. Restore roles through the platform's supported provisioning process; do not create production auth roles ad hoc. |
| `cannot change return type of existing function` | Save `pg_get_functiondef` and dependent-object output. During a maintenance window, drop/recreate only after confirming the deployed signature is obsolete and no caller depends on it. Never use `CASCADE`. |
| `duplicate key value violates unique constraint` after the explicit audit | Treat this as unreviewed schema/trigger drift or an unexpected race. The table lock should prevent auth writes. Roll back, inspect constraints/triggers and the conflicting rows, repair through the data process above, then retry. |
| `deadlock detected` | PostgreSQL rolls back the transaction. Keep writes paused, capture the server deadlock report, remove the competing migration/write path, and retry from the beginning. |
| Connection loss or client cancellation | Commit status is unknown. Reconnect, run the post-migration verification query, and inspect the migration log. Because the script is retry-safe, rerun the entire bounded transaction if and only if committed state cannot be established. |

## Rollback and recovery

The preferred rollback is application-only: disable Google auth, roll back the
backend/frontend release, and leave the new database functions and unambiguous
identity backfill in place. They are compatible with the earlier schema. Do not
restore the old email-based auto-link behavior while Google auth is enabled.

If a database-function rollback is required:

1. Disable Google login and Settings linking first. No new backend instance may
   call `resolve_google_login` while it is being removed.
2. Restore the pre-deploy `link_google_identity` definition and remove only the
   new resolver in one transaction:

   ```sh
   psql "$DATABASE_URL" -X -v ON_ERROR_STOP=1 --single-transaction \
     -c "set local lock_timeout = '10s';" \
     -f link_google_identity.predeploy.sql \
     -c "drop function if exists public.resolve_google_login(text,text,text,text);"
   ```

3. Verify the restored function owner and `service_role` grant before enabling
   any compatible application version.
4. Do not delete backfilled `user_identities` rows as a blanket rollback. They
   preserve valid stable-subject evidence and are compatible with the old
   schema. Reverse an individual row only after the same ownership review used
   for a repair.
5. Use the full logical backup or Supabase PITR only for catastrophic data
   corruption. A point-in-time restore affects all writes after the restore
   point and requires the normal incident/reconciliation process.

An error before `COMMIT` needs no database rollback: the single transaction
restores the pre-migration state automatically.

## Manual production verification still required

Automated tests do not complete production verification. Record the `users.id`,
row counts, HTTP status/code, and timestamp for each check.

### Web

1. Start with a verified password account that has no Google identity. Confirm
   its profile/games and record its `users.id`.
2. Attempt Google login with the same verified email. Expect
   `409 ACCOUNT_LINK_REQUIRED`, actionable Settings guidance, no JWT, no new
   user, and no identity mutation.
3. Sign in with the password, open Settings, and connect that Google account.
   Expect one identity row, unchanged `users.id`/email/profile/game ownership,
   and no change to `tokens_valid_after` from linking.
4. Repeat the same Settings link. Expect success/idempotent state with still one
   identity row.
5. Sign out, then use Google login. Expect the original `users.id` and unchanged
   application data. Password login must still return the same user.
6. Verify a Google subject or provider email already owned by a different user
   returns `409` with no mutation.
7. Verify a genuinely new Google identity creates exactly one user and one
   identity, and concurrent/repeated login returns that same user.
8. Verify invalid tokens return `401` and unverified Google email claims return
   `403`, with no database mutation.

### Android

1. Install the signed production build on a physical device registered with the
   production package/SHA configuration. Confirm the native plugin uses the
   production web OAuth client ID.
2. Repeat the password-account conflict, password login, Settings link, logout,
   and native Google login sequence. All successful methods must return the
   original `users.id` and preserve profile/game ownership.
3. Verify English and Hebrew `ACCOUNT_LINK_REQUIRED` guidance and confirm it is
   not classified as user cancellation.
4. Cancel the native picker and expect neutral cancellation feedback. Exercise
   provider/configuration, network, `401`/`403`, and `5xx` failures and confirm
   safe feedback plus cleanup of partial session state.
5. Confirm the app JWT is stored only in secure storage, logout clears it, and
   Android/application logs contain no Google ID token, access token, app JWT,
   credential payload, or email address.

The issue remains open until these production checks are recorded successfully.
