# Tasks: Multi-User Web

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~2200-2600 (6 slices x ~350-450) |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 -> PR 2 -> PR 3 -> PR 4 -> PR 5 -> PR 6 |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending (user decision) |

Decision needed before apply: Yes (resolved)
Chained PRs recommended: Yes
Chain strategy: stacked-to-main (resolved — PR 2 of 6 in progress)
400-line budget risk: High

Ask the user: **Stacked PRs to main** (each slice mergeable alone, matches the design's numbered slices) or **Feature Branch Chain** (a `multi-user-web` tracker accumulates all 6 before merging)? OWNER tasks (Phase 0) are prerequisites, not PR content, and run outside the line budget.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Schema, RLS, keepalive, Edge skeleton | PR 1 | N/A (SQL/TS, no pytest yet) | Manual `supabase start` checklist | Drop `supabase/` additions |
| 2 | Browser auth + sealed-box + api.ts | PR 2 | `npm run build --prefix web` | Manual sign-up/in in dev server | Revert `web/src/api*`, `AuthGate` |
| 3 | Python Supabase adapter + `book-all` loop | PR 3 | `.venv\Scripts\python.exe -m pytest -q` | N/A: batch needs live UPV window, validated by tests + fakes | Revert `app/run_batch.py`, `adapters/supabase_rest.py`, `book.yml` |
| 4 | Refresh: Edge rate-limit + Realtime | PR 4 | `.venv\Scripts\python.exe -m pytest -q` + `npm run build --prefix web` | Manual refresh button against `supabase start` | Revert `refresh.yml`, `useRefreshStatus.ts` |
| 5 | Pages deploy + Vite `base` | PR 5 | `npm run build --prefix web` | Visit deployed Pages URL | Revert `vite.config.ts`, `pages.yml` |
| 6 | Migration + docs | PR 6 | N/A (docs + owner run) | OWNER runs `book-all --now` for own account | Revert README; cron body stays on old mode |

## Phase 0: OWNER Prerequisites (manual, outside agent scope)

- [ ] OWNER 0.1 Create the Supabase project (free tier)
- [ ] OWNER 0.2 Run `seal-keygen` (Phase 3), store the private key as GitHub secret `SEAL_PRIVATE_KEYS`
- [ ] OWNER 0.3 Set GitHub secrets: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_SEAL_PUBLIC_KEY`, `VITE_SEAL_KEY_ID`, dispatch PAT
- [ ] OWNER 0.4 Enable GitHub Pages (source: GitHub Actions) in repo settings
- [ ] OWNER 0.5 Configure cron-job.org: Saturday 09:45 Europe/Madrid dispatch (`book-all`) and daily keepalive dispatch

## Phase 1: Schema, RLS, Keepalive, Edge Skeleton (PR 1)

Satisfies: user-accounts (RLS isolation, deletion cascade), booking-queue (limits, RLS), platform-operations (keepalive).

- [x] 1.1 Create `supabase/migrations/0001_multi_user.sql`: tables, RLS policies, `validate_queue` trigger, `batch_roster()`, `claim_refresh()`, `keepalive` RPC, Realtime publication
- [x] 1.2 Create `supabase/functions/refresh/index.ts` skeleton: `getUser()`, CORS limited to Pages origin
- [x] 1.3 Create `supabase/functions/delete-account/index.ts`: `auth.admin.deleteUser` via service role
- [x] 1.4 Create `.github/workflows/keepalive.yml`: `workflow_dispatch` + `schedule` backup, calls `rpc/keepalive`
- [ ] OWNER 1.5 Apply the migration and deploy both Edge Functions to the live Supabase project

## Phase 2: Browser Auth + Sealed-Box + api.ts (PR 2)

Satisfies: user-accounts (sign-up/in), credential-custody (browser sealing).

- [x] 2.1 Add `@supabase/supabase-js`, `libsodium-wrappers` to `web/package.json`
- [x] 2.2 Create `web/src/api/local.ts`, `web/src/api/supabase.ts`; keep `web/src/api.ts` as the `VITE_BACKEND` facade
- [x] 2.3 Create `web/src/seal.ts` (lazy import): `crypto_box_seal` against `VITE_SEAL_PUBLIC_KEY`/`VITE_SEAL_KEY_ID`
- [x] 2.4 Create `web/src/components/AuthGate.tsx`, `SignIn.tsx`, `CredentialsForm.tsx`
- [x] 2.5 Modify `web/src/App.tsx`, `web/src/main.tsx`: wrap the app in `AuthGate`
- [x] 2.6 Test: `npm run build --prefix web`

## Phase 3: Python Supabase Adapter + `book-all` Loop (PR 3)

Satisfies: weekly-batch-booking (turn-taking, isolation, results, email), credential-custody (unsealing, logs), platform-operations (log hygiene).

- [ ] 3.1 RED `tests/test_run_batch.py`: user B login fails, A and C still processed and recorded
- [ ] 3.2 RED `tests/test_run_batch.py`: empty queue produces no result row and no email
- [ ] 3.3 RED `tests/test_turns.py`: `TurnScheduler` keeps exactly one active user; a retrying user does not starve others
- [ ] 3.4 RED `tests/test_sealed_box.py`: interop fixture sealed by libsodium-wrappers opens with PyNaCl; wrong/unknown `key_id` raises `CredentialsUnavailable`
- [ ] 3.5 RED `tests/test_log_redaction.py`: `caplog` has no codes/usernames/emails after `RedactingFilter`
- [ ] 3.6 Add `UserDirectory`, `CredentialOpener` protocols to `src/upv_auto/ports.py`
- [ ] 3.7 Create `src/upv_auto/app/turns.py`: `TurnScheduler`, `TurnTakingClock`, `BufferedNotifier`
- [ ] 3.8 Create `src/upv_auto/app/run_batch.py`: roster loop, per-user `dataclasses.replace(config, ...)`, try/record per user
- [ ] 3.9 Create `src/upv_auto/adapters/supabase_rest.py`: httpx PostgREST client, service-role key
- [ ] 3.10 Create `src/upv_auto/adapters/sealed_box.py`: PyNaCl opener + `seal-keygen` command
- [ ] 3.11 Create `src/upv_auto/adapters/log_redaction.py`: `RedactingFilter`, `httpx` logger at WARNING
- [ ] 3.12 Modify `src/upv_auto/__main__.py`: add `book-all [--now]`, `seal-keygen` subcommands
- [ ] 3.13 Modify `pyproject.toml`: extra `multiuser = ["pynacl>=1.5"]`
- [ ] 3.14 Modify `.github/workflows/book.yml`: `book-all` mode, Supabase/seal secrets, no artifact upload, fixed `run-name`
- [ ] 3.15 Test: `.venv\Scripts\python.exe -m pytest -q`

## Phase 4: Refresh — Edge Rate-Limit + Realtime (PR 4)

Satisfies: schedule-refresh (throttle, rate limit, loading state), credential-custody (no plaintext logs).

- [ ] 4.1 RED `tests/test_refresh_user.py`: `refresh --request-id` rejects a non-UUID value (threat matrix: workflow-input injection)
- [ ] 4.2 Finish `supabase/functions/refresh/index.ts`: `getUser()` -> `claim_refresh` -> `workflow_dispatch(request_id)` only
- [ ] 4.3 Create `.github/workflows/refresh.yml`: UUID input validated via `env`, `timeout-minutes: 10`, no `concurrency:` group, no artifacts
- [ ] 4.4 Create `src/upv_auto/app/refresh_user.py`: unseal -> `fetch_schedule` -> save; status `done`/`failed`
- [ ] 4.5 Modify `src/upv_auto/__main__.py`: add `refresh --request-id` subcommand
- [ ] 4.6 Create `web/src/api/useRefreshStatus.ts`: Realtime hook on `refresh_requests`; wire sign-in throttle and manual-button triggers
- [ ] 4.7 Modify `web/src/App.tsx`: drive `refreshing` from `useRefreshStatus`
- [ ] 4.8 Test: `.venv\Scripts\python.exe -m pytest -q` and `npm run build --prefix web`

## Phase 5: Pages Deploy + Vite `base` (PR 5)

Satisfies: platform-operations (Pages hosting).

- [ ] 5.1 Modify `web/vite.config.ts`: `base: process.env.VITE_BASE_PATH ?? "/"`
- [ ] 5.2 Create `.github/workflows/pages.yml`: build `web/`, deploy to Pages
- [ ] 5.3 Create `web/src/scheduleView.ts`: port `build_days` to TypeScript
- [ ] 5.4 Verify `VITE_BACKEND=local` still serves FastAPI for `serve --demo`
- [ ] 5.5 Test: `npm run build --prefix web` with `VITE_BASE_PATH` set

## Phase 6: Migration + Docs (PR 6)

- [ ] 6.1 Modify `README.md`: setup, key rotation, migration, local dev
- [ ] OWNER 6.2 Sign up on the deployed Pages URL, enter credentials and the queue for the current user
- [ ] OWNER 6.3 Run `book-all --now` scoped to this one account to validate end-to-end
- [ ] OWNER 6.4 Switch the cron-job.org batch body to `mode: book-all`
- [ ] OWNER 6.5 After one successful Saturday, delete the `UPV_USERNAME`/`UPV_PASSWORD` secrets
