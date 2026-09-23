# Exploration: multi-user-web

Full exploration is also persisted in Engram (`sdd/multi-user-web/explore`).

## Goal (confirmed)

Turn the single-user tool into a multi-user web app other UPV students use from a URL, at zero cost (free tiers, no credit card):

- Front: existing React/Vite app on GitHub Pages. No backend server; FastAPI stays only as a local-dev driver.
- Supabase free: email auth, Postgres (queues, cached schedule, per-user state) with RLS, Realtime, and an Edge Function that dispatches GitHub workflows.
- UPV credentials sealed in the browser (libsodium sealed box, public key); the private key lives only as a GitHub Actions secret.
- GitHub Actions is the only component that logs into UPV: Saturday batch for all users (cron-job.org → `workflow_dispatch`, 09:45 Europe/Madrid) and per-user schedule refresh triggered on sign-in (throttled) and by a manual button (rate-limited). No periodic refresh.
- Daily keepalive ping so Supabase free does not pause.
- Public repo: workflows never print usernames, group codes or per-user details.

## Current state

- `domain/`, `ports.py`, `app/` use cases take exactly one `Credentials` / `Notifier` / `AppConfig` per call: reusable per user unchanged; only the driver must loop.
- Adapters `playwright_auth`, `httpx_session`, `httpx_booking`, `upv_activities_parser`, `email` work on one identity and are reusable as-is (`EmailNotifier` recipient becomes per user).
- `config.py` is the single-user persistence boundary (env credentials, `config.yaml` queue rewritten by `save_bookings`, `LimitsConfig` 10/6).
- `adapters/web/api.py` has one in-process `ScheduleStore` with no user key; no auth.
- `web/src/api.ts` uses same-origin `fetch('/api/*')`; `App.tsx` already has a skeleton (`!schedule`) and `refreshing` spinner; `QueuePanelSkeleton.tsx` is the loading-state hook point.
- `web/vite.config.ts` has no `base` (GitHub Pages project path would 404).
- `.github/workflows/book.yml`: `workflow_dispatch` only, `concurrency: book`, `timeout-minutes: 30`, one set of secrets.

## Approaches for the Saturday batch

1. Sequential loop over users in one job — reuses the engine untouched, one audited log path, avoids simultaneous CAS logins. Cost: runtime grows linearly (~10-20 s login per user); must fit the timeout. Effort: low.
2. Matrix job per user — parallel and isolated, but untested against UPV throttling, more log surface. Effort: medium.

## Recommendation

Approach 1 for v1 (matrix later is additive). Keep the UPV `activity` global (one shared activity, as today) for v1.

Phased delivery (~400-line slices):

1. Supabase schema + RLS + keepalive + Edge Function skeleton.
2. Browser auth + sealed-box encryption; `api.ts` against Supabase.
3. Python Supabase adapter (PyNaCl unseal, queue read) + `book.yml` sequential multi-user loop.
4. Per-user refresh: Edge Function auth/rate-limit, sign-in + manual triggers, Realtime driving the loading state.
5. GitHub Pages deploy + Vite `base`; FastAPI becomes local-dev only; README.
6. Migrate the current user; cleanup of `config.yaml`-as-production docs.

## Risks

- New deps: `libsodium-wrappers` (web) and `PyNaCl` (Python); both implement `crypto_box_seal`, so they interoperate.
- Edge Function auth (`auth.uid()`) and rate limiting are new code.
- Per-user failure isolation: one user's error must not abort the batch; per-user results must be recorded.
- Public logs need an explicit audit for the multi-user loop.
- One shared Gmail sender emails N users: check sending limits.
- Account deletion needs cascade deletes.
- Timeout and concurrency of `book.yml` must be re-validated for N users.
- The Supabase anon key in the front is public by design (RLS-protected).
