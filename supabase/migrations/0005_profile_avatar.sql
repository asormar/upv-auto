-- Profile photo: a small image stored in the profile row itself.
--
-- The browser shrinks the photo to a few KB before saving, so a column is
-- enough: no storage bucket, no public URLs, and a photo is only ever
-- readable by its owner and by accepted friends through `list_friends()`.
-- The check keeps the column to what an <img> can safely show: a bounded
-- base64 data URL of a raster format (no SVG).

alter table public.profiles
  add column avatar text
  check (
    avatar is null
    or (
      length(avatar) <= 30000
      and avatar ~ '^data:image/(webp|jpeg|png);base64,[A-Za-z0-9+/=]+$'
    )
  );

grant update (avatar) on public.profiles to authenticated;

-- A function's result columns cannot change in place, so it is replaced.
-- Same body as 0004 plus the friend's photo, filled for accepted friends only
-- (a pending request shows an alias, never a photo).
drop function public.list_friends();

create function public.list_friends()
returns table (
  friendship_id uuid,
  friend_alias text,
  relation text,
  group_codes text[],
  friend_avatar text
)
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
    end,
    case when f.status = 'accepted' then p.avatar else null end
  from public.friendships f
  join public.profiles p
    on p.user_id = case when f.requester_id = auth.uid() then f.addressee_id else f.requester_id end
  where auth.uid() in (f.requester_id, f.addressee_id)
  order by lower(p.alias), f.created_at;
$$;

revoke all on function public.list_friends() from public;
grant execute on function public.list_friends() to authenticated;

notify pgrst, 'reload schema';
