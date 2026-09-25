-- claim_refresh: tell the caller whether a workflow run must be dispatched.
--
-- 0001's version returned an already-pending request as-is, so the Edge
-- Function dispatched `refresh.yml` again for a request a previous run was
-- already processing. The duplicate run then found the request no longer
-- pending (or already finished) and failed, which surfaced as a red
-- "Refresh schedule" run and a failure email for a refresh that had, in
-- fact, worked.
--
-- The claim rules themselves are unchanged; only the return shape is.

drop function if exists public.claim_refresh(text);

create function public.claim_refresh(p_trigger text)
returns table (id uuid, dispatch boolean)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id uuid := auth.uid();
  v_now timestamptz := now();
  v_pending public.refresh_requests;
  v_last_done timestamptz;
  v_manual_recent int;
  v_manual_today int;
  v_result public.refresh_requests;
begin
  if v_user_id is null then
    raise exception 'claim_refresh requires an authenticated user';
  end if;

  if p_trigger not in ('signin', 'manual') then
    raise exception 'invalid trigger: %', p_trigger;
  end if;

  perform pg_advisory_xact_lock(hashtext(v_user_id::text));

  -- Stale pending requests stop blocking new ones after 15 minutes.
  update public.refresh_requests
  set status = 'failed', error_code = 'expired', finished_at = v_now
  where user_id = v_user_id
    and status = 'pending'
    and created_at < v_now - interval '15 minutes';

  select * into v_pending
  from public.refresh_requests
  where user_id = v_user_id and status = 'pending'
  order by created_at desc
  limit 1;

  if found then
    -- Already being processed by a running workflow: the caller keeps
    -- showing the pending state, but must not dispatch a second run.
    return query select v_pending.id, false;
    return;
  end if;

  if p_trigger = 'signin' then
    select finished_at into v_last_done
    from public.refresh_requests
    where user_id = v_user_id and status = 'done'
    order by finished_at desc
    limit 1;

    if v_last_done is not null and v_last_done > v_now - interval '6 hours' then
      return;
    end if;
  else
    select count(*) into v_manual_recent
    from public.refresh_requests
    where user_id = v_user_id
      and trigger = 'manual'
      and created_at > v_now - interval '5 minutes';

    if v_manual_recent > 0 then
      return;
    end if;

    select count(*) into v_manual_today
    from public.refresh_requests
    where user_id = v_user_id
      and trigger = 'manual'
      and created_at > v_now - interval '1 day';

    if v_manual_today >= 10 then
      return;
    end if;
  end if;

  insert into public.refresh_requests (user_id, trigger, status)
  values (v_user_id, p_trigger, 'pending')
  returning * into v_result;

  return query select v_result.id, true;
end;
$$;

revoke all on function public.claim_refresh(text) from public;
grant execute on function public.claim_refresh(text) to authenticated;
