-- Two fixes: refresh abuse, and the queue limit the trigger never saw.
--
-- 1. claim_refresh. Under 0003 the 'signin' trigger was only throttled after a
--    successful ('done') refresh, there was no daily cap on it, and nothing
--    checked that the caller had credentials at all. A user with none, or with
--    ones UPV rejects, therefore got a 'failed' request on every sign-in, each
--    one dispatching a GitHub Actions run (a minute or more of runner time)
--    and, for rejected credentials, another login attempt against UPV's CAS:
--    a path to locking the account out.
--
--    What changes (everything else, including the signature, security
--    definer, search_path, the advisory lock, the 15-minute expiry, the
--    pending reuse and "dispatch = true only for a newly inserted row", is
--    as in 0003):
--
--    a. No `upv_credentials` row for the caller -> nothing is claimed, for
--       every trigger. There is nothing a run could unseal, so it could only
--       fail. (The web saves the credentials before it asks for a
--       'credentials' refresh, so that path always has its row.)
--
--    b. 'signin' is throttled by the last refresh that actually reached UPV,
--       whether it ended 'done' or 'failed' (6 hours, the same window as
--       before). Requests that never got that far ('expired' and
--       'dispatch_failed') do not count, so a GitHub outage does not silence
--       the sign-in refresh for the next six hours.
--
--    c. A cap of 12 requests per rolling 24 hours, counting every request of
--       the user whatever its trigger or outcome (failed ones included), for
--       'signin' and 'manual'. The 6-hour window already limits sign-in runs
--       to 4 a day, so 12 leaves honest use (a few sign-ins and a handful of
--       manual refreshes) untouched while bounding the runs one account can
--       cause to a small, fixed number.
--
--    'credentials' is exempt from (b) and (c) and keeps only the 10-a-day cap
--    it had in 0003: a user fixing rejected credentials must always be able to
--    re-check them, and a bound on that path already exists.
--
--    The Edge Function needs no change for the new "nothing claimed" cases:
--    it already answers `{ dispatched: false }` (200) to an empty 'signin'
--    claim and 429 `rate_limited` to the others, and the web clears its
--    loading state on both.
--
-- 2. validate_queue. It read `max_per_activity` from the top level of
--    `app_settings.settings`, but `book-all` / `refresh` publish it as
--    `limits.max_per_activity` (the shape the web reads too), so the trigger
--    always fell back to 6. It now reads the nested key first, then the old
--    top-level one, then 6. Everything else in it is unchanged.

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
  v_last_attempt timestamptz;
  v_total_today int;
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

  -- Without stored credentials a run has nothing to unseal and can only fail.
  perform 1 from public.upv_credentials where user_id = v_user_id;
  if not found then
    return;
  end if;

  if p_trigger <> 'credentials' then
    select count(*) into v_total_today
    from public.refresh_requests
    where user_id = v_user_id
      and created_at > v_now - interval '1 day';

    if v_total_today >= 12 then
      return;
    end if;
  end if;

  if p_trigger = 'signin' then
    -- The last refresh that really ran against UPV, successful or not. One
    -- that never got there ('expired', 'dispatch_failed') does not count.
    select max(coalesce(finished_at, created_at)) into v_last_attempt
    from public.refresh_requests
    where user_id = v_user_id
      and (
        status = 'done'
        or (status = 'failed' and coalesce(error_code, '') not in ('expired', 'dispatch_failed'))
      );

    if v_last_attempt is not null and v_last_attempt > v_now - interval '6 hours' then
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

revoke all on function public.claim_refresh(text) from public, anon;
grant execute on function public.claim_refresh(text) to authenticated, service_role;

create or replace function public.validate_queue()
returns trigger
language plpgsql
as $$
declare
  v_max_per_activity int;
  v_booking jsonb;
  v_seen text[] := '{}';
  v_preferred text;
  v_alt jsonb;
  v_alt_code text;
begin
  select coalesce(
      (settings #>> '{limits,max_per_activity}')::int,
      (settings ->> 'max_per_activity')::int,
      6
    )
    into v_max_per_activity
    from public.app_settings
    where id = 1;

  if v_max_per_activity is null then
    v_max_per_activity := 6;
  end if;

  if jsonb_typeof(new.bookings) is distinct from 'array' then
    raise exception 'bookings must be a JSON array';
  end if;

  if jsonb_array_length(new.bookings) > v_max_per_activity then
    raise exception
      'Queue exceeds the UPV limit of % bookings for this activity', v_max_per_activity;
  end if;

  for v_booking in select * from jsonb_array_elements(new.bookings)
  loop
    v_preferred := v_booking ->> 'group_code';

    if v_preferred is null or v_preferred !~ '^[A-Z]{3}[0-9]{3}$' then
      raise exception 'Invalid group_code: %', coalesce(v_preferred, 'null');
    end if;

    if v_preferred = any (v_seen) then
      raise exception 'Duplicate preferred group_code in queue: %', v_preferred;
    end if;
    v_seen := array_append(v_seen, v_preferred);

    if v_booking ? 'alternatives' then
      for v_alt in select * from jsonb_array_elements(v_booking -> 'alternatives')
      loop
        v_alt_code := v_alt #>> '{}';
        if v_alt_code is null or v_alt_code !~ '^[A-Z]{3}[0-9]{3}$' then
          raise exception 'Invalid alternative group_code: %', coalesce(v_alt_code, 'null');
        end if;
      end loop;
    end if;
  end loop;

  new.updated_at := now();
  return new;
end;
$$;
