-- Live friend requests: the page hears about changes to `friendships`
-- (a new request, an accepted one, a removal) instead of waiting for a reload.
--
-- Realtime applies each subscriber's own RLS policy to inserts and updates,
-- so a user is only told about rows `friendships select own` lets them read.
-- A delete carries just the primary key (the default replica identity), which
-- is all the page needs to know it must read the list again.

do $$
begin
  if not exists (
    select 1
    from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'friendships'
  ) then
    alter publication supabase_realtime add table public.friendships;
  end if;
end;
$$;
