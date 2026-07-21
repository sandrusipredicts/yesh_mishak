-- ISSUE-882: Atomic account deletion RPC function.
--
-- Wraps token revocation, game-counter reconciliation, and user row deletion
-- in a single transaction so the operation is all-or-nothing.
--
-- The user row deletion triggers ON DELETE CASCADE for owned rows
-- (game_players, push_tokens, notifications, etc.) and ON DELETE SET NULL
-- for shared records (fields.added_by, games.created_by, etc.).
--
-- Game counter reconciliation mirrors the leave_game logic: decrement
-- players_present, reopen games that drop below max_players.

create or replace function public.delete_user_account(p_user_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_game record;
    v_new_count integer;
    v_new_status text;
    v_reconciled integer := 0;
begin
    -- 1. Revoke all sessions (set tokens_valid_after to now)
    update users
    set tokens_valid_after = now()
    where id = p_user_id;

    if not found then
        return jsonb_build_object('error', 'user_not_found');
    end if;

    -- 2. Reconcile game counters for active games
    for v_game in
        select g.id, g.players_present, g.max_players, g.status
        from games g
        join game_players gp on gp.game_id = g.id
        where gp.user_id = p_user_id
          and g.status in ('open', 'full')
    loop
        v_new_count := greatest(0, v_game.players_present - 1);
        v_new_status := case
            when v_new_count < v_game.max_players then 'open'
            else v_game.status
        end;

        update games
        set players_present = v_new_count,
            status = v_new_status
        where id = v_game.id;

        v_reconciled := v_reconciled + 1;
    end loop;

    -- 3. Delete the user row (CASCADE handles dependent rows)
    delete from users where id = p_user_id;

    return jsonb_build_object(
        'deleted', true,
        'games_reconciled', v_reconciled
    );
end;
$$;

revoke all on function public.delete_user_account(uuid) from public, anon, authenticated;
grant execute on function public.delete_user_account(uuid) to service_role;
