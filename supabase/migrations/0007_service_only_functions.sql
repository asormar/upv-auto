-- Lock the service-only functions, and keep anonymous visitors off the rest.
--
-- 0001 closed `batch_roster()` and `keepalive()` with `revoke all ... from
-- public` and a grant to `service_role`. That is not enough on Supabase:
-- its default privileges grant EXECUTE on every new function in `public`
-- directly to `anon` and `authenticated`, and revoking from `public` does not
-- touch those direct grants. With only the anon key (which ships in the web
-- build) anyone could call `rpc/batch_roster` and read every user's email,
-- sealed credentials and bookings. Only `service_role` may run these two.
--
-- The functions below are meant for signed-in users, and each is keyed on
-- `auth.uid()`, so an anonymous caller gets nothing useful from them. Taking EXECUTE away from `anon` changes
-- nothing for them (the browser and the `refresh` Edge Function call them
-- with the user's session) and just stops anonymous requests reaching them.

revoke execute on function public.batch_roster() from anon, authenticated;
revoke execute on function public.keepalive() from anon, authenticated;
grant execute on function public.batch_roster() to service_role;
grant execute on function public.keepalive() to service_role;

revoke execute on function public.claim_refresh(text) from anon;
revoke execute on function public.send_friend_request(text) from anon;
revoke execute on function public.respond_friend_request(uuid, boolean) from anon;
revoke execute on function public.list_friends() from anon;
