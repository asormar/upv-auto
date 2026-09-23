// Refresh Edge Function — skeleton (Phase 1).
//
// Finished in Phase 4: `getUser()` -> `claim_refresh()` -> dispatch
// `refresh.yml` with `request_id` only (see design.md). This skeleton only
// authenticates the caller and answers CORS preflight, so the function can
// already be deployed and referenced by the frontend before Phase 4 lands.

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
  const authHeader = req.headers.get("Authorization") ?? "";

  // Verify the caller under their own session (never the service role):
  // only a signed-in user may claim a refresh, and only for themselves.
  const supabase = createClient(supabaseUrl, supabaseAnonKey, {
    global: { headers: { Authorization: authHeader } },
  });

  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser();

  if (authError || !user) {
    return jsonResponse({ error: "unauthorized" }, 401, origin);
  }

  // TODO (Phase 4): parse `{ trigger: "signin" | "manual" }`, call
  // `rpc/claim_refresh`, and on a non-null claim dispatch `refresh.yml`
  // with `request_id` as the only input. A null claim means the caller is
  // throttled (sign-in) or rate-limited (manual) and must not dispatch.
  return jsonResponse({ error: "not_implemented" }, 501, origin);
});
