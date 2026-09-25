-- A third refresh trigger: 'credentials'.
--
-- Saving new UPV credentials must always be able to re-check them. Under
-- 0002 that refresh went through the 'manual' rules, so a user who had just
-- refreshed (or whose credentials had just been rejected) hit the 5-minute
-- limit, no run was dispatched, and the app kept showing the result of the
-- old credentials — indistinguishable from "changing them does nothing".
--
-- 'credentials' skips the 5-minute rule (the user cannot fix a rejected
-- login any other way) but keeps a daily cap, so a broken password cannot
-- become an unbounded login loop against UPV's CAS.

alter table public.refresh_requests
  drop constraint if exists refresh_requests_trigger_check;

alter table public.refresh_requests
  add constraint refresh_requests_trigger_check
  check (trigger in ('signin', 'manual', 'credentials'));

create or replace function public.claim_refresh(p_trigger text)
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
  v_credentials_today int;
  v_result public.refresh_requests;
begin
  if v_user_id is null then
    raise exception 'claim_refresh requires an authenticated user';
  end if;

  if p_trigger not in ('signin', 'manual', 'credentials') then
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
    -- Already being processed: keep the pending state, dispatch nothing.
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
  elsif p_trigger = 'credentials' then
    select count(*) into v_credentials_today
    from public.refresh_requests
    where user_id = v_user_id
      and trigger = 'credentials'
      and created_at > v_now - interval '1 day';

    if v_credentials_today >= 10 then
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
