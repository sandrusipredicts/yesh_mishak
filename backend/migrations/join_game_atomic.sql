-- ISSUE-021: Atomic join_game RPC function + belt-and-suspenders CHECK constraint.
--
-- Consistency model:
-- 1. The Postgres function join_game_atomic() runs inside a single transaction.
-- 2. SELECT ... FOR UPDATE locks the game row, preventing concurrent readers
--    from seeing stale players_present until this transaction commits/rolls back.
-- 3. All validation (status, capacity, duplicate) happens AFTER the lock,
--    so two concurrent callers are serialized — the second sees the first's update.
-- 4. The game_players INSERT and games UPDATE happen in the same transaction,
--    so they either both commit or both roll back.
-- 5. The CHECK constraint is a final safety net: even if application code
--    bypasses the RPC, Postgres itself will reject players_present > max_players.

-- Safety-net constraint: players_present can never exceed max_players
alter table games
    add constraint check_players_within_limit
    check (players_present <= max_players);

-- Atomic join function
create or replace function join_game_atomic(p_game_id uuid, p_user_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_game record;
    v_already_joined boolean;
    v_new_players_present integer;
    v_new_status text;
    v_result jsonb;
begin
    -- Lock the game row to serialize concurrent joins
    select *
    into v_game
    from games
    where id = p_game_id
    for update;

    if not found then
        return jsonb_build_object('error', 'Game not found');
    end if;

    -- Check game is active (open or full, not finished/cancelled)
    if v_game.status not in ('open', 'full') then
        return jsonb_build_object('error', 'Game already closed');
    end if;

    -- Check capacity
    if v_game.players_present >= v_game.max_players then
        return jsonb_build_object('error', 'Game is full');
    end if;

    -- Check duplicate
    select exists(
        select 1 from game_players
        where game_id = p_game_id and user_id = p_user_id
    ) into v_already_joined;

    if v_already_joined then
        return jsonb_build_object('error', 'User already joined');
    end if;

    -- Insert player
    insert into game_players (game_id, user_id) values (p_game_id, p_user_id);

    -- Update game counters
    v_new_players_present := v_game.players_present + 1;
    v_new_status := case
        when v_new_players_present >= v_game.max_players then 'full'
        else 'open'
    end;

    update games
    set players_present = v_new_players_present,
        status = v_new_status
    where id = p_game_id;

    -- Return the updated game row
    select to_jsonb(g) into v_result
    from games g
    where g.id = p_game_id;

    return jsonb_build_object('game', v_result);
end;
$$;

-- Grant execute to authenticated users and service_role
grant execute on function join_game_atomic(uuid, uuid) to authenticated;
grant execute on function join_game_atomic(uuid, uuid) to service_role;
