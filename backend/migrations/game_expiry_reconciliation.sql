-- E03-01: Scheduled game expiry reconciliation.
-- Safe to re-run. Apply before enabling the Railway cron job.

create index if not exists idx_games_expiry_reconciliation
    on public.games(expires_at, id)
    where status in ('open', 'full')
      and expires_at is not null;

create or replace function public.reconcile_expired_games(
    p_cutoff timestamptz default pg_catalog.now(),
    p_batch_size integer default 100
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_batch_size integer := greatest(1, least(coalesce(p_batch_size, 100), 1000));
    v_scanned_count integer := 0;
    v_reconciled_count integer := 0;
    v_reconciled_game_ids uuid[] := array[]::uuid[];
begin
    with candidates as (
        select id
        from public.games
        where status in ('open', 'full')
          and expires_at is not null
          and expires_at <= p_cutoff
        order by expires_at asc, id asc
        limit v_batch_size
        for update skip locked
    ),
    counted as (
        select count(*)::integer as scanned_count
        from candidates
    ),
    updated as (
        update public.games g
        set status = 'finished'
        from candidates c
        where g.id = c.id
          and g.status in ('open', 'full')
          and g.expires_at is not null
          and g.expires_at <= p_cutoff
        returning g.id
    )
    select
        counted.scanned_count,
        coalesce(count(updated.id), 0)::integer,
        coalesce(array_agg(updated.id order by updated.id) filter (where updated.id is not null), array[]::uuid[])
    into v_scanned_count, v_reconciled_count, v_reconciled_game_ids
    from counted
    left join updated on true
    group by counted.scanned_count;

    return jsonb_build_object(
        'scanned_count', coalesce(v_scanned_count, 0),
        'reconciled_count', coalesce(v_reconciled_count, 0),
        'skipped_count', greatest(coalesce(v_scanned_count, 0) - coalesce(v_reconciled_count, 0), 0),
        'reconciled_game_ids', coalesce(to_jsonb(v_reconciled_game_ids), '[]'::jsonb),
        'cutoff', p_cutoff
    );
end;
$$;

grant execute on function public.reconcile_expired_games(timestamptz, integer) to service_role;
