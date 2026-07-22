-- Fetch the complete game portion of GET /fields in one PostgREST request.
-- Expired games are reconciled in the same transaction so map state is fresh.
begin;

create or replace function public.get_field_game_payloads(p_field_ids uuid[])
returns table(payload jsonb)
language plpgsql
security invoker
set search_path = public
as $$
begin
    update public.games
       set status = 'finished'
     where field_id = any(p_field_ids)
       and status in ('open', 'full')
       and expires_at is not null
       and expires_at <= now();

    return query
    select to_jsonb(g) || jsonb_build_object(
        'participants',
        coalesce(
            (
                select jsonb_agg(
                    jsonb_build_object(
                        'user_id', gp.user_id,
                        'username', u.username,
                        'name', coalesce(u.username, u.name, 'Unknown player')
                    )
                    order by gp.joined_at, gp.id
                )
                  from public.game_players gp
                  left join public.users u on u.id = gp.user_id
                 where gp.game_id = g.id
            ),
            '[]'::jsonb
        )
    )
      from public.games g
     where g.field_id = any(p_field_ids)
       and g.status in ('open', 'full');
end;
$$;

revoke all on function public.get_field_game_payloads(uuid[]) from public;
revoke all on function public.get_field_game_payloads(uuid[]) from anon;
revoke all on function public.get_field_game_payloads(uuid[]) from authenticated;
grant execute on function public.get_field_game_payloads(uuid[]) to service_role;

commit;
