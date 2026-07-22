# GET /fields (Sentry: `GET fields-map`) performance audit

Audit date: 2026-07-22. Source of truth: `origin/main` at `7801161`.

## Code path and outbound requests

`app.main` includes `app.routers.fields.router`; `GET /fields/` enters
`fields.get_fields`. The handler validates optional bounds, loads public fields,
loads related game payloads, then attaches `active_game` and `upcoming_games` by
`field_id` in memory. There is no authentication dependency on this public read.

Before this change, the latest code performed:

1. One bounded `fields` select, or `ceil(field_count / 1000)` sequential field
   page selects when bounds were absent or incomplete.
2. `ceil(field_count / 100)` sequential `games` selects because field IDs were
   split into batches of 100.
3. One `game_players` select per 100 visible games.
4. One `users` select per 100 distinct participants.
5. One `games` update per expired game encountered during the read.

No reports, notifications, storage objects, or signed image URLs are requested.
The field select uses `*`, so stored field metadata and `image_url` are returned,
but no image HTTP request is made by the backend.

The observed approximately 14 sequential GETs are consistent with the second
step for roughly 1,300 returned fields. The implementation was batched N+1
rather than literally one request per field, but outbound request count still
grew linearly in 100-field increments and the batches ran sequentially.

## Request-count model

For fields with no games and a single fields page:

| Returned fields | Before | After |
| ---: | ---: | ---: |
| 1 | 2 | 2 |
| 10 | 2 | 2 |
| 50 | 2 | 2 |
| 1,357 | 16 (2 field pages + 14 game batches) | 3 (2 field pages + 1 RPC) |

Before, fields with games could add participant, user, and expired-game update
requests. After, one `get_field_game_payloads` RPC fetches games and participant
identities and reconciles expired games transactionally. A normal bounded map
request therefore makes exactly two outbound data requests regardless of field,
game, or participant count: one fields select and one RPC.

## Bounds and indexes

Bounds are applied only when all four of `north`, `south`, `east`, and `west`
are present. Partial or absent bounds intentionally fall back to the paginated
full public listing. Antimeridian-crossing bounds are rejected. Public rows must
be verified, approved, open, and have `removed_at is null`.

The schema contains the matching partial index
`idx_fields_public_active_spatial (lat, lng)` for that exact public predicate,
plus `idx_games_field_id_status`, `idx_game_players_game_id`, and the users
primary-key index used by the RPC joins.

## Payload and compatibility

Map markers themselves need only identity, coordinates, display name, sport,
and active state. The same list response is also used immediately by the field
details/game panels, notifications field selection, deep links, Android, and
iOS. Those consumers require field metadata, upcoming games, participant lists,
and participant counts. The public response contract is therefore preserved;
payload slimming should be a separately versioned marker/detail API change.

## Timing evidence

Production baseline supplied with this audit: 8.31 seconds total, approximately
8.15 seconds in outbound HTTP and 155 ms server self time. The change reduces
the trace-shaped 14 related-data GETs to one RPC (plus the fields request). A
simple latency projection using the observed average outbound span gives about
1.32 seconds total (`8.15 / 14 * 2 + 0.155`), before accounting for the RPC's
in-database joins. This is a projection, not production proof. Actual p50/p95
must be recorded after the migration and application deploy have accumulated
sufficient Sentry samples; caching is deliberately not introduced.

## RPC security correction

The initial migration explicitly granted the mutating RPC to `anon` and
`authenticated` and did not revoke PostgreSQL's default `PUBLIC` function
execution privilege. That would have allowed holders of the public anon key to
invoke expired-game reconciliation directly.

The permanent design is service-role-only:

- the public field select continues to use the regular Supabase client;
- only `get_field_game_payloads` uses the backend-only service-role client;
- the service-role key remains confined to Railway/backend configuration and is
  never exposed to frontend, Android, or iOS code;
- the function remains `SECURITY INVOKER` with `search_path = public`;
- all table references are schema-qualified;
- `PUBLIC`, `anon`, and `authenticated` have all function privileges revoked;
- only `service_role` receives `EXECUTE`.

The migration is wrapped in `begin`/`commit`. Applying it defines the function
and privileges but does not invoke it, so it performs no migration-time game
update. Expired games are still reconciled transactionally only during a later
RPC request.

## Deployment and rollback order

Deployment order is strict:

1. Verify the target is an isolated non-production Supabase project matching
   the intended non-production backend configuration.
2. Apply `backend/migrations/fields_map_payload_rpc.sql` in full.
3. Verify the function signature and confirm `PUBLIC`, `anon`, and
   `authenticated` cannot execute it while `service_role` can.
4. Deploy the backend containing the service-role RPC caller.
5. Run contract/request-count smoke tests and collect timing evidence.
6. Repeat for production only after non-production validation and approval.

Rollback order avoids an availability gap:

1. Restore/deploy the previous backend so no running instance depends on the
   RPC.
2. Revoke function execution from every role.
3. Drop `public.get_field_game_payloads(uuid[])` if removal is desired.

Dropping the RPC does not alter table data, but it cannot undo games already
correctly transitioned to `finished`. After deployment, privilege verification
must use `has_function_privilege` for `PUBLIC`, `anon`, `authenticated`, and
`service_role`; expected results are `false`, `false`, `false`, and `true`.
