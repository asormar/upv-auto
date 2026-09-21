-- Multi-user schema: per-user tables under RLS, one global settings row,
-- and the SQL surface the batch job, the refresh Edge Function, and the
-- daily keepalive job call through.
--
-- Every per-user table stores `user_id uuid references auth.users(id)
-- on delete cascade`, and each user policy is `user_id = auth.uid()`, so
-- deleting the auth user (see `supabase/functions/delete-account`) removes
-- every row that user owns. `service_role` always bypasses RLS in
-- Supabase, so tables below grant no explicit service-role policies.

-- ============================================================
-- app_settings: the one global table, no `user_id`. Seeded here so an
-- empty read never breaks the app before the first batch run upserts the
-- real values from `config.yaml`.
-- ============================================================

create table public.app_settings (
  id smallint primary key default 1 check (id = 1),
  settings jsonb not null default '{}'::jsonb
);

alter table public.app_settings enable row level security;

create policy "app_settings readable by signed-in users"
  on public.app_settings
  for select
  to authenticated
  using (true);

insert into public.app_settings (id, settings)
values (1, '{}'::jsonb)
on conflict (id) do nothing;

-- ============================================================
-- upv_credentials: sealed UPV credentials, never plaintext (see
-- credential-custody spec). Only the owning user can read/write their row;
-- only the GitHub Actions runner ever unseals the ciphertext.
-- ============================================================

create table public.upv_credentials (
  user_id uuid primary key references auth.users (id) on delete cascade,
  sealed text not null,
  key_id text not null,
  updated_at timestamptz not null default now()
);

alter table public.upv_credentials enable row level security;

create policy "upv_credentials select own"
  on public.upv_credentials for select
  using (user_id = auth.uid());

create policy "upv_credentials insert own"
  on public.upv_credentials for insert
  with check (user_id = auth.uid());

create policy "upv_credentials update own"
  on public.upv_credentials for update
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

create policy "upv_credentials delete own"
  on public.upv_credentials for delete
  using (user_id = auth.uid());

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

create trigger upv_credentials_touch_updated_at
  before update on public.upv_credentials
  for each row
  execute function public.touch_updated_at();

-- ============================================================
-- booking_queue: one row per user, an ordered JSON array of bookings.
-- `validate_queue()` below enforces the UPV limit and code shape.
-- ============================================================

create table public.booking_queue (
  user_id uuid primary key references auth.users (id) on delete cascade,
  bookings jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now()
);

alter table public.booking_queue enable row level security;

create policy "booking_queue select own"
  on public.booking_queue for select
  using (user_id = auth.uid());

create policy "booking_queue insert own"
  on public.booking_queue for insert
  with check (user_id = auth.uid());

create policy "booking_queue update own"
  on public.booking_queue for update
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

-- Enforces the UPV limit: at most `max_per_activity` (default 6) bookings
-- per user; alternatives do not count towards the limit. Also enforces the
-- group code shape (`^[A-Z]{3}\d{3}$`, matching
-- `upv_auto.config.validate_group_code`) and unique preferred codes.
-- `max_per_activity` is read from `app_settings` when the owner has
-- upserted it from `config.yaml`, defaulting to 6 (the UPV rule) so the
-- trigger works before the first batch run seeds that row.
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
  select coalesce((settings ->> 'max_per_activity')::int, 6)
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

create trigger booking_queue_validate
  before insert or update on public.booking_queue
  for each row
  execute function public.validate_queue();

-- ============================================================
-- schedules: cached activity groups per user. The runner (service role)
-- writes; the owning user only reads. Raw groups, no `booking_path`
-- (the client derives booking state from the live queue).
-- ============================================================

create table public.schedules (
  user_id uuid primary key references auth.users (id) on delete cascade,
  groups jsonb not null default '{}'::jsonb,
  fetched_at timestamptz
);

alter table public.schedules enable row level security;

create policy "schedules select own"
  on public.schedules for select
  using (user_id = auth.uid());

-- ============================================================
-- refresh_requests: one row per refresh attempt, claimed through
-- `claim_refresh()` below so rate limiting is atomic. Users only ever
-- read their own rows (driving the Realtime loading state); only
-- `claim_refresh()` (security definer) inserts, and only the service
-- role (the `refresh` Edge Function / `refresh.yml`) updates.
-- ============================================================

create table public.refresh_requests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  trigger text not null check (trigger in ('signin', 'manual')),
  status text not null default 'pending' check (status in ('pending', 'done', 'failed')),
  error_code text,
  created_at timestamptz not null default now(),
  finished_at timestamptz
);

create index refresh_requests_user_status_idx
  on public.refresh_requests (user_id, status, created_at desc);

alter table public.refresh_requests enable row level security;

create policy "refresh_requests select own"
  on public.refresh_requests for select
  using (user_id = auth.uid());

-- Claims (or reuses) a refresh request for the calling user, enforcing:
-- sign-in throttle (skip if the last `done` refresh finished under 6h
-- ago), manual rate limit (1 per 5 min, 10 per day), pending-request
-- reuse, and expiry of pending requests older than 15 minutes. Returns
-- the request row to dispatch, or NULL when the caller should not get a
-- new refresh (throttled, rate-limited). `pg_advisory_xact_lock` per user
-- serializes concurrent claims so two racing requests cannot both pass
-- the checks below.
create or replace function public.claim_refresh(p_trigger text)
returns public.refresh_requests
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
    return v_pending;
  end if;

  if p_trigger = 'signin' then
    select finished_at into v_last_done
    from public.refresh_requests
    where user_id = v_user_id and status = 'done'
    order by finished_at desc
    limit 1;

    if v_last_done is not null and v_last_done > v_now - interval '6 hours' then
      return null;
    end if;
  else
    select count(*) into v_manual_recent
    from public.refresh_requests
    where user_id = v_user_id
      and trigger = 'manual'
      and created_at > v_now - interval '5 minutes';

    if v_manual_recent > 0 then
      return null;
    end if;

    select count(*) into v_manual_today
    from public.refresh_requests
    where user_id = v_user_id
      and trigger = 'manual'
      and created_at > v_now - interval '1 day';

    if v_manual_today >= 10 then
      return null;
    end if;
  end if;

  insert into public.refresh_requests (user_id, trigger, status)
  values (v_user_id, p_trigger, 'pending')
  returning * into v_result;

  return v_result;
end;
$$;

revoke all on function public.claim_refresh(text) from public;
grant execute on function public.claim_refresh(text) to authenticated;

-- Drives the frontend's loading state (schedule-refresh spec).
alter publication supabase_realtime add table public.refresh_requests;

-- ============================================================
-- batch_results: one row per user per batch run. Users only read their
-- own rows; only the service role (the `book-all` runner) inserts.
-- ============================================================

create table public.batch_results (
  id bigint generated by default as identity primary key,
  user_id uuid not null references auth.users (id) on delete cascade,
  run_id text not null,
  status text not null check (status in ('booked', 'incomplete', 'credentials_unavailable', 'error')),
  summary text not null default '',
  created_at timestamptz not null default now()
);

create index batch_results_user_idx on public.batch_results (user_id, created_at desc);

alter table public.batch_results enable row level security;

create policy "batch_results select own"
  on public.batch_results for select
  using (user_id = auth.uid());

-- ============================================================
-- batch_roster(): the `book-all` runner's entry point. Returns every user
-- with a non-empty queue, joined with their sealed credentials and email,
-- so the runner can unseal and attempt a booking. Executable only by the
-- service role: it exposes every user's sealed credentials and email in
-- one call, which must never be reachable from the anon/authenticated key.
-- ============================================================

create or replace function public.batch_roster()
returns table (
  user_id uuid,
  email text,
  sealed text,
  key_id text,
  bookings jsonb
)
language sql
security definer
set search_path = public
as $$
  select q.user_id, u.email, c.sealed, c.key_id, q.bookings
  from public.booking_queue q
  join auth.users u on u.id = q.user_id
  join public.upv_credentials c on c.user_id = q.user_id
  where jsonb_array_length(q.bookings) > 0;
$$;

revoke all on function public.batch_roster() from public;
grant execute on function public.batch_roster() to service_role;

-- ============================================================
-- keepalive(): pinged daily so the Supabase free project is not
-- auto-paused for inactivity. A trivial read is enough to count as
-- project activity; it touches no per-user data.
-- ============================================================

create or replace function public.keepalive()
returns void
language sql
security definer
set search_path = public
as $$
  select 1 from public.app_settings limit 1;
$$;

revoke all on function public.keepalive() from public;
grant execute on function public.keepalive() to service_role;
