-- Friends: a shareable friend code per user, mutual friendships that need
-- the other side's acceptance, and one read surface (`list_friends`) that
-- shows an accepted friend's queue.
--
-- A friend's `booking_queue` row stays unreadable under its own RLS policy
-- (0001). `list_friends()` is the only door: it returns the preferred group
-- codes and nothing else, so alternatives never leave their owner. Friend
-- codes are never returned for other users either; they are looked up inside
-- `send_friend_request()`.

-- ============================================================
-- profiles: friend code + alias, one row per user.
-- ============================================================

-- 8 characters from an alphabet without look-alikes (no 0/O, 1/I/L), drawn
-- from `gen_random_uuid()` bytes so it does not depend on pgcrypto.
create or replace function public.generate_friend_code()
returns text
language plpgsql
volatile
as $$
declare
  c_alphabet constant text := 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
  v_bytes bytea;
  v_code text;
  i int;
begin
  loop
    v_bytes := decode(replace(gen_random_uuid()::text, '-', ''), 'hex');
    v_code := '';
    for i in 0..7 loop
      v_code := v_code || substr(c_alphabet, (get_byte(v_bytes, i) % length(c_alphabet)) + 1, 1);
    end loop;
    exit when not exists (select 1 from public.profiles where friend_code = v_code);
  end loop;
  return v_code;
end;
$$;

create table public.profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  friend_code text not null unique,
  alias text not null check (char_length(btrim(alias)) between 1 and 24),
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

create policy "profiles select own"
  on public.profiles for select
  using (user_id = auth.uid());

-- Users may rename themselves, never touch their code or owner: the grant is
-- column-level, the policy keeps it to their own row. Rows are created by the
-- trigger below, so there is no insert or delete policy.
create policy "profiles update own"
  on public.profiles for update
  using (user_id = auth.uid())
  with check (user_id = auth.uid());

revoke update on public.profiles from authenticated, anon;
grant update (alias) on public.profiles to authenticated;

create or replace function public.create_profile_for_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  v_code text := public.generate_friend_code();
begin
  insert into public.profiles (user_id, friend_code, alias)
  values (new.id, v_code, 'Amigo ' || substr(v_code, 1, 4));
  return new;
end;
$$;

create trigger on_auth_user_created_profile
  after insert on auth.users
  for each row
  execute function public.create_profile_for_new_user();

-- Users that signed up before this migration.
do $$
declare
  v_user record;
  v_code text;
begin
  for v_user in
    select u.id from auth.users u
    where not exists (select 1 from public.profiles p where p.user_id = u.id)
  loop
    v_code := public.generate_friend_code();
    insert into public.profiles (user_id, friend_code, alias)
    values (v_user.id, v_code, 'Amigo ' || substr(v_code, 1, 4));
  end loop;
end;
$$;

-- ============================================================
-- friendships: one row per pair, whoever asked first. Created and accepted
-- only through the functions below; either side may delete it (decline,
-- cancel, or unfriend).
-- ============================================================

create table public.friendships (
  id uuid primary key default gen_random_uuid(),
  requester_id uuid not null references auth.users (id) on delete cascade,
  addressee_id uuid not null references auth.users (id) on delete cascade,
  status text not null default 'pending' check (status in ('pending', 'accepted')),
  created_at timestamptz not null default now(),
  check (requester_id <> addressee_id)
);

-- One row per pair, in either direction.
create unique index friendships_pair_key
  on public.friendships (least(requester_id, addressee_id), greatest(requester_id, addressee_id));

create index friendships_addressee_idx on public.friendships (addressee_id);

alter table public.friendships enable row level security;

create policy "friendships select own"
  on public.friendships for select
  using (auth.uid() in (requester_id, addressee_id));

create policy "friendships delete own"
  on public.friendships for delete
  using (auth.uid() in (requester_id, addressee_id));

revoke insert, update on public.friendships from authenticated, anon;

-- ============================================================
-- Friend operations. Errors are stable codes the client translates.
-- ============================================================

-- Returns 'requested', or 'accepted' when the other side had already asked
-- (two people adding each other's code just become friends).
create or replace function public.send_friend_request(p_code text)
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  v_me uuid := auth.uid();
  v_target uuid;
  v_existing public.friendships;
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

  insert into public.friendships (requester_id, addressee_id) values (v_me, v_target);
  return 'requested';
end;
$$;

-- Only the addressee answers; declining removes the row so it can be asked
-- again later.
create or replace function public.respond_friend_request(p_friendship_id uuid, p_accept boolean)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_me uuid := auth.uid();
begin
  if v_me is null then
    raise exception 'not_signed_in';
  end if;

  if p_accept then
    update public.friendships set status = 'accepted'
      where id = p_friendship_id and addressee_id = v_me and status = 'pending';
  else
    delete from public.friendships
      where id = p_friendship_id and addressee_id = v_me and status = 'pending';
  end if;

  if not found then
    raise exception 'request_not_found';
  end if;
end;
$$;

-- Everyone connected to the caller. `group_codes` is the friend's queue as
-- preferred codes in queue order, filled only for accepted friends.
create or replace function public.list_friends()
returns table (friendship_id uuid, friend_alias text, relation text, group_codes text[])
language sql
stable
security definer
set search_path = public
as $$
  select
    f.id,
    p.alias,
    case
      when f.status = 'accepted' then 'friend'
      when f.addressee_id = auth.uid() then 'incoming'
      else 'outgoing'
    end,
    case
      when f.status = 'accepted' then (
        select coalesce(array_agg(e.booking ->> 'group_code' order by e.idx), '{}'::text[])
        from public.booking_queue q
        cross join lateral jsonb_array_elements(q.bookings) with ordinality as e(booking, idx)
        where q.user_id = p.user_id
      )
      else '{}'::text[]
    end
  from public.friendships f
  join public.profiles p
    on p.user_id = case when f.requester_id = auth.uid() then f.addressee_id else f.requester_id end
  where auth.uid() in (f.requester_id, f.addressee_id)
  order by lower(p.alias), f.created_at;
$$;

revoke all on function public.send_friend_request(text) from public;
revoke all on function public.respond_friend_request(uuid, boolean) from public;
revoke all on function public.list_friends() from public;
grant execute on function public.send_friend_request(text) to authenticated;
grant execute on function public.respond_friend_request(uuid, boolean) to authenticated;
grant execute on function public.list_friends() to authenticated;
