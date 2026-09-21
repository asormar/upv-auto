// Delete-account Edge Function.
//
// Removes the caller's own auth user via `auth.admin.deleteUser`, which
// requires the service role. Every per-user table in
// `supabase/migrations/0001_multi_user.sql` references `auth.users(id) on
// delete cascade`, so this single call also removes the user's sealed
// credentials, queue, cached schedule, refresh requests, and batch
// results (user-accounts spec: "Account Deletion Cascade").

import { createClient } from "npm:@supabase/supabase-js@2";
import { corsHeaders, jsonResponse } from "../_shared/cors.ts";

Deno.serve(async (req) => {
  const origin = req.headers.get("origin");

  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders(origin) });
  }

  if (req.method !== "POST") {
    return jsonResponse({ error: "method_not_allowed" }, 405, origin);
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
  const supabaseAnonKey = Deno.env.get("SUPABASE_ANON_KEY")!;
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const authHeader = req.headers.get("Authorization") ?? "";

  // Identify the caller under their own session first: only a signed-in
  // user may delete an account, and only their own — the service role
  // below is used solely for the admin delete call, never to look up
  // which user to delete.
  const callerClient = createClient(supabaseUrl, supabaseAnonKey, {
    global: { headers: { Authorization: authHeader } },
  });

  const {
    data: { user },
    error: authError,
  } = await callerClient.auth.getUser();

  if (authError || !user) {
    return jsonResponse({ error: "unauthorized" }, 401, origin);
  }

  const adminClient = createClient(supabaseUrl, serviceRoleKey);
  const { error: deleteError } = await adminClient.auth.admin.deleteUser(user.id);

  if (deleteError) {
    return jsonResponse({ error: "delete_failed" }, 500, origin);
  }

  return jsonResponse({ ok: true }, 200, origin);
});
