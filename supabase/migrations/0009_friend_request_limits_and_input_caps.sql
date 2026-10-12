-- Hardening of three user-controlled inputs: friend requests, aliases, and the
-- size of a queue.
--
-- 1. send_friend_request. Under 0004 anyone with a friend code could send as
--    many requests as they liked, ask again the moment they were declined, and
--    two requests crossing between the same pair surfaced a raw
--    `unique_violation` instead of one of the codes the web translates.
--
--    A declined request is a deleted `friendships` row (see
--    `respond_friend_request`), so nothing remembers it, and neither does a
--    request its sender cancelled. Counting `friendships` rows would therefore
--    let a send/cancel loop go unnoticed, and a cooldown would have nothing to
--    read. Instead of adding a status to `friendships` (which Realtime, RLS,
--    `list_friends` and the web all read) this adds a small private log that
--    only the two functions below touch: one row per request sent, stamped
--    when the addressee declines it.
--
--    What changes (the signature, security definer, search_path and the codes
--    `not_signed_in`, `friend_code_not_found`, `cannot_friend_self`,
--    `already_friends` and `request_already_sent` are as in 0004):
--
--    a. At most 20 requests sent per user per rolling hour, declined or
--       cancelled ones included (`friend_rate_limited`). Adding a few friends
--       in a row is nowhere near it, while a script walking friend codes or
--       flooding one person with notifications hits it in seconds. Accepting a
--       request the other side already made is not a send and does not count.
--
--    b. After a decline, the same sender cannot ask the same person again for
--       24 hours (`request_cooldown`). Only that direction: the decliner may
--       still ask the other one, and an existing request from the other side
--       is still accepted. Requests declined before this migration were never
--       logged, so they get no cooldown.
--
--    c. Two requests crossing at the same moment no longer fail with a raw
--       `unique_violation`: the loser re-reads the pair and answers as if it
--       had come second (`accepted` if the other side's request landed first,
--       `request_already_sent` if its own did).
--
--    The sender's calls are serialised with an advisory lock so a burst of
--    parallel calls cannot slip past the hourly count.
--
-- 2. profiles.alias. The check measured `btrim(alias)`, so a value with any
--    amount of surrounding whitespace passed and was stored as is. It now
--    measures the stored value itself. Existing aliases are trimmed (and cut
--    to 24 characters if need be) first so the new check applies cleanly.
--
-- 3. validate_queue. A queue was bounded in length but not in size: one entry
--    could carry an arbitrarily long `alternatives` list. `bookings` is now
--    capped at 16 KiB, far above the largest real queue (a handful of 6
--    character codes). Everything else in it is as in 0008.

-- ============================================================
-- Log of friend requests sent. Private: RLS on and no policy, and no grant to
-- the API roles, so only the security definer functions below can see it.
-- ============================================================

create table public.friend_request_log (
  id bigint generated always as identity primary key,
  requester_id uuid not null references auth.users (id) on delete cascade,
  addressee_id uuid not null references auth.users (id) on delete cascade,
  created_at timestamptz not null default now(),
  declined_at timestamptz
);

create index friend_request_log_requester_idx
  on public.friend_request_log (requester_id, created_at desc);

alter table public.friend_request_log enable row level security;

revoke all on public.friend_request_log from public, anon, authenticated;

-- ============================================================
-- send_friend_request: hourly cap, cooldown after a decline, no raw
-- unique_violation.
-- ============================================================

create or replace function public.send_friend_request(p_code text)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  c_hourly_cap constant int := 20;
  c_cooldown constant interval := interval '24 hours';
  v_me uuid := auth.uid();
  v_target uuid;
  v_existing public.friendships;
  v_attempt int;
begin
  if v_me is null then
    raise exception 'not_signed_in';
  end if;

  select user_id into v_target
    from public.profiles
    where friend_code = upper(btrim(p_code));

  if v_target is null then
    raise exception 'friend_code_not_found';
  end if;
  if v_target = v_me then
    raise exception 'cannot_friend_self';
  end if;

  -- One send at a time per sender, so the count below cannot be outrun.
  perform pg_advisory_xact_lock(hashtext('send_friend_request:' || v_me::text));

  -- The log only has to reach back past the cooldown; keep it from growing.
  delete from public.friend_request_log
    where requester_id = v_me and created_at < now() - interval '7 days';

  -- A second pass is only needed when a request from the other side lands
  -- between the lookup and the insert.
  for v_attempt in 1..2 loop
    select * into v_existing
      from public.friendships
      where (requester_id = v_me and addressee_id = v_target)
         or (requester_id = v_target and addressee_id = v_me);

    if found then
      if v_existing.status = 'accepted' then
        raise exception 'already_friends';
      elsif v_existing.requester_id = v_me then
        raise exception 'request_already_sent';
      end if;
      update public.friendships set status = 'accepted' where id = v_existing.id;
      return 'accepted';
    end if;

    if exists (
      select 1 from public.friend_request_log
      where requester_id = v_me
        and addressee_id = v_target
        and declined_at > now() - c_cooldown
    ) then
      raise exception 'request_cooldown';
    end if;

    if (
      select count(*) from public.friend_request_log
      where requester_id = v_me and created_at > now() - interval '1 hour'
    ) >= c_hourly_cap then
      raise exception 'friend_rate_limited';
    end if;

    begin
      insert into public.friendships (requester_id, addressee_id) values (v_me, v_target);
    exception when unique_violation then
      continue;
    end;

    insert into public.friend_request_log (requester_id, addressee_id) values (v_me, v_target);
    return 'requested';
  end loop;

  -- Still colliding after re-reading: a request between the pair exists.
  raise exception 'request_already_sent';
end;
$$;

-- Only the addressee answers; declining removes the row so it can be asked
-- again later (after the cooldown above). Same as 0004 plus the decline being
-- recorded in the log.
create or replace function public.respond_friend_request(p_friendship_id uuid, p_accept boolean)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_me uuid := auth.uid();
  v_requester uuid;
begin
  if v_me is null then
    raise exception 'not_signed_in';
  end if;

  if p_accept then
    update public.friendships set status = 'accepted'
      where id = p_friendship_id and addressee_id = v_me and status = 'pending';
    if not found then
      raise exception 'request_not_found';
    end if;
  else
    delete from public.friendships
      where id = p_friendship_id and addressee_id = v_me and status = 'pending'
      returning requester_id into v_requester;
    if v_requester is null then
      raise exception 'request_not_found';
    end if;

    update public.friend_request_log set declined_at = now()
      where requester_id = v_requester and addressee_id = v_me and declined_at is null;
  end if;
end;
$$;

revoke all on function public.send_friend_request(text) from public, anon;
revoke all on function public.respond_friend_request(uuid, boolean) from public, anon;
grant execute on function public.send_friend_request(text) to authenticated;
grant execute on function public.respond_friend_request(uuid, boolean) to authenticated;

-- ============================================================
-- profiles.alias: the stored value is what is measured.
-- ============================================================

update public.profiles
  set alias = btrim(left(btrim(alias), 24))
  where alias is distinct from btrim(left(btrim(alias), 24));

alter table public.profiles drop constraint if exists profiles_alias_check;

alter table public.profiles
  add constraint profiles_alias_check
  check (char_length(alias) between 1 and 24 and btrim(alias) <> '');

-- ============================================================
-- validate_queue: cap the payload. As in 0008 otherwise.
-- ============================================================

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

  if pg_column_size(new.bookings) > 16384 then
    raise exception 'Queue payload is too large (limit 16384 bytes)';
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
