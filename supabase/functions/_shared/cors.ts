// Shared CORS handling for the multi-user Edge Functions. Every function in
// this app is only ever called from the deployed GitHub Pages frontend, so
// the allowed origin is a single fixed value, not a wildcard.
//
// Set the `ALLOWED_ORIGIN` function secret to the deployed Pages origin,
// e.g. `https://<owner>.github.io` (no trailing slash, no path). Local dev
// against `supabase start` can set it to `http://localhost:5173`.

const ALLOWED_ORIGIN = Deno.env.get("ALLOWED_ORIGIN") ?? "";

/**
 * Builds the CORS response headers. The allowed origin is fixed
 * (`ALLOWED_ORIGIN`), so a request from any other origin still gets this
 * header back; the browser is the one that refuses to expose the response
 * to a caller whose origin does not match.
 */
export function corsHeaders(_requestOrigin: string | null): HeadersInit {
  return {
    "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
    "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    // The origin varies per deployment (Pages vs local dev), so downstream
    // caches must not reuse a response across different origins.
    Vary: "Origin",
  };
}

/** JSON response helper that always includes the CORS headers. */
export function jsonResponse(
  body: unknown,
  status: number,
  requestOrigin: string | null,
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders(requestOrigin), "Content-Type": "application/json" },
  });
}
