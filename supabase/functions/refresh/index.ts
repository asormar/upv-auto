// Refresh Edge Function (schedule-refresh spec).
//
// `getUser()` -> `rpc/claim_refresh` -> `workflow_dispatch(request_id)` only
// (design.md's "Refresh dispatch" decision). `claim_refresh` is a security
// definer SQL function that owns every rate-limit rule (sign-in throttle,
// manual 5min/day limits, pending reuse/expiry) atomically, so this function
// never re-implements or second-guesses those checks — a `null` claim always
// means "do not dispatch", and this function decides only how to answer the
// caller for that case.
//
// Set these function secrets (`supabase secrets set`), never GitHub Actions
// secrets: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`,
// `ALLOWED_ORIGIN` (see `_shared/cors.ts`), `GITHUB_REPO` ("owner/repo"),
// `GITHUB_DISPATCH_TOKEN` (a fine-grained PAT scoped to Actions:write on
// that one repo only — OWNER 0.3's "dispatch PAT").

import { createClient } from "npm:@supabase/supabase-js@2";
import { corsHeaders, jsonResponse } from "../_shared/cors.ts";

interface ClaimResult {
  id: string;
  /** False when an earlier run is already processing this request: the
   * caller keeps its pending state, but a second dispatch would race that
   * run and fail (migration 0002). */
  dispatch: boolean;
}

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
  // only a signed-in user may claim a refresh, and only for themselves —
  // `claim_refresh` reads `auth.uid()` from this same session, so a caller
  // can never claim a refresh on someone else's behalf.
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

  let trigger: unknown;
  try {
    const body = await req.json();
    trigger = body?.trigger;
  } catch {
    return jsonResponse({ error: "invalid_body" }, 400, origin);
  }

  if (trigger !== "signin" && trigger !== "manual" && trigger !== "credentials") {
    return jsonResponse({ error: "invalid_trigger" }, 400, origin);
  }

  const { data: claimRows, error: claimError } = await supabase.rpc("claim_refresh", {
    p_trigger: trigger,
  });

  if (claimError) {
    return jsonResponse({ error: "claim_failed" }, 500, origin);
  }

  const claimed: ClaimResult | null = (claimRows as ClaimResult[] | null)?.[0] ?? null;

  // Already pending: nothing to dispatch, but this is not a rejection —
  // the caller's loading state is correct as it stands.
  if (claimed && !claimed.dispatch) {
    return jsonResponse({ dispatched: true, request_id: claimed.id }, 200, origin);
  }

  if (!claimed) {
    // Sign-in throttle: silent, the cached schedule is still served
    // (schedule-refresh spec's "Sign-in within throttle window uses
    // cache"). Manual: the caller is explicitly rejected (schedule-refresh
    // spec's "Manual refresh rejected when rate-limited").
    if (trigger === "signin") {
      return jsonResponse({ dispatched: false }, 200, origin);
    }
    return jsonResponse({ error: "rate_limited" }, 429, origin);
  }

  const githubRepo = Deno.env.get("GITHUB_REPO");
  const dispatchToken = Deno.env.get("GITHUB_DISPATCH_TOKEN");
  if (!githubRepo || !dispatchToken) {
    return jsonResponse({ error: "dispatch_not_configured" }, 500, origin);
  }

  // Only the opaque request id ever leaves this function as a workflow
  // input — never the user id or email (design.md's "Refresh dispatch"
  // decision: "Public run inputs show only a random UUID").
  const dispatchResponse = await fetch(
    `https://api.github.com/repos/${githubRepo}/actions/workflows/refresh.yml/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${dispatchToken}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: "main", inputs: { request_id: claimed.id } }),
    },
  );

  if (!dispatchResponse.ok) {
    // Best-effort: mark the claim failed so it does not sit `pending` for
    // the full 15-minute expiry window, silently blocking a retry via
    // `claim_refresh`'s pending-request reuse.
    const serviceClient = createClient(supabaseUrl, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    await serviceClient
      .from("refresh_requests")
      .update({ status: "failed", error_code: "dispatch_failed", finished_at: new Date().toISOString() })
      .eq("id", claimed.id);
    return jsonResponse({ error: "dispatch_failed" }, 502, origin);
  }

  return jsonResponse({ dispatched: true, request_id: claimed.id }, 200, origin);
});
