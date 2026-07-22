-- E10-08: Google Play compliant permanent app-account deletion.
-- Safe to re-run. The service role can invoke this narrowly scoped RPC but
-- does not receive broad DELETE privileges on public.users.

create or replace function public.delete_user_account(p_user_id uuid)
returns table (result text)
language plpgsql
security definer
set search_path = public
as $$
begin
    if not exists (select 1 from public.users where id = p_user_id) then
        return query select 'user_not_found'::text;
        return;
    end if;

    delete from public.users where id = p_user_id;
    return query select 'deleted'::text;
end;
$$;

revoke all on function public.delete_user_account(uuid) from public;
grant execute on function public.delete_user_account(uuid) to service_role;
