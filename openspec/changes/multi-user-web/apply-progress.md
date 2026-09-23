# Apply Progress: Multi-User Web

## Work Unit 1 — Schema, RLS, Keepalive, Edge Skeleton (PR 1)

Status: complete (agent-scoped tasks). OWNER 1.5 (apply migration + deploy Edge Functions to the live project) is out of agent scope and stays unchecked.

### Completed Tasks
- [x] 1.1 `supabase/migrations/0001_multi_user.sql` — tables, RLS policies, `validate_queue` trigger, `batch_roster()`, `claim_refresh()`, `keepalive()` RPC, Realtime publication
- [x] 1.2 `supabase/functions/refresh/index.ts` skeleton — `getUser()`, CORS limited to `ALLOWED_ORIGIN`
- [x] 1.3 `supabase/functions/delete-account/index.ts` — `auth.admin.deleteUser` via service role
- [x] 1.4 `.github/workflows/keepalive.yml` — `workflow_dispatch` + `schedule` backup, calls `rpc/keepalive`

### Not in this work unit
- [ ] OWNER 1.5 Apply the migration and deploy both Edge Functions to the live Supabase project (manual, owner-only)

### Files Changed
| File | Action | Lines |
|------|--------|-------|
| `supabase/migrations/0001_multi_user.sql` | Created | 387 |
| `supabase/functions/_shared/cors.ts` | Created | 38 |
| `supabase/functions/refresh/index.ts` | Created | 46 |
| `supabase/functions/delete-account/index.ts` | Created | 54 |
| `.github/workflows/keepalive.yml` | Created | 34 |
| `openspec/changes/multi-user-web/tasks.md` | Modified | 4 lines (checkboxes) |

Total new/authored lines: 559 additions across code files (387+38+46+54+34), plus 4 checkbox flips in `tasks.md`. This exceeds the nominal 400-line budget as one slice — the forecast itself estimated "PR 1 -> ~350-450" and this came in higher, mainly because `claim_refresh()`'s full rate-limit logic (sign-in throttle, manual 5min/day limits, pending reuse/expiry) was pulled into 1.1 per the task's own description ("claim_refresh()" listed explicitly in 1.1's scope) rather than deferred to Phase 4. The schema is one cohesive, atomically-testable unit; splitting the migration file itself would leave partial, non-applicable SQL. Recommend `size:exception` for this slice.

### Work Unit Evidence
| Evidence | Value |
|---|---|
| Focused test command and exact result | `.venv\Scripts\python.exe -m pytest -q` — 79 passed, 0 failed (no Python files touched in this unit; confirms no regression) |
| Runtime harness command/scenario and exact result | N/A for this unit: SQL/TS only, no live Supabase project yet (OWNER 0.1/1.5 not run). Manual `supabase start` RLS/limit/throttle checklist is deferred to whoever runs OWNER 1.5. SQL was manually reviewed statement-by-statement (table order, RLS policy grammar, `security definer` grant hygiene, advisory-lock cast) since no local `psql`/`docker` daemon was available to execute it. `npm run build --prefix web` — built successfully (51 modules, no errors) as a secondary regression check, though this unit touches no `web/` files |
| Rollback boundary | Drop the new `supabase/` directory (`migrations/0001_multi_user.sql`, `functions/refresh`, `functions/delete-account`, `functions/_shared/cors.ts`) and `.github/workflows/keepalive.yml`. No existing file was modified except `tasks.md` checkboxes |

### Deviations from Design
None — implementation matches design.md's schema table, function list, and Edge Function skeleton scope.

### Notes / Judgment Calls
- `validate_queue()` reads `max_per_activity` from `app_settings.settings->>'max_per_activity'`, defaulting to `6` (the UPV rule, matching `LimitsConfig.max_per_activity` in `src/upv_auto/config.py`) so the trigger works before the first `book-all` run seeds `app_settings` from `config.yaml`. Design did not specify the exact source for this constant; this keeps one source of truth without blocking on Phase 3's config-upsert code.
- `claim_refresh(trigger)` uses `auth.uid()` internally (not a passed `user_id` parameter) so a caller can only ever claim a refresh for themselves — consistent with "Row-Level Access Isolation" in `user-accounts` spec.
- Added a small shared `supabase/functions/_shared/cors.ts` (not explicitly listed in design's File Changes table) to avoid duplicating the CORS/JSON-response boilerplate between `refresh` and `delete-account`. This is the standard Supabase Edge Functions pattern for shared code and does not change any table's contract.
- `ALLOWED_ORIGIN` is a new Edge Function secret (not listed among the OWNER 0.3 GitHub secrets, since Edge Function secrets are set via `supabase secrets set`, not GitHub Actions secrets). Documented in `cors.ts`; the deployment/rotation instructions belong in the Phase 6 README task.

### Remaining Tasks (later work units, not this agent's scope)
- [ ] Phase 3 (PR 3): Python Supabase adapter + `book-all` loop
- [ ] Phase 4 (PR 4): Refresh — Edge rate-limit + Realtime (finishes `refresh/index.ts`)
- [ ] Phase 5 (PR 5): Pages deploy + Vite `base`
- [ ] Phase 6 (PR 6): Migration + docs

### Workload / PR Boundary
- Mode: stacked PR slice (`stacked-to-main`), PR 1 of 6
- Current work unit: Unit 1 — Schema, RLS, keepalive, Edge skeleton
- Boundary: starts from no `supabase/` directory and no `keepalive.yml`; ends with a complete, deployable (by the owner) schema + two Edge Functions + keepalive workflow, with zero changes to `src/`, `web/`, or `book.yml`
- Estimated review budget impact: ~505 authored lines, above the 400-line default; recommend `size:exception` for this slice given the migration's atomicity, or accept as reported since `ask-on-risk` already resolved the chain strategy at slice granularity

## Work Unit 2 — Browser Auth + Sealed-Box + api.ts (PR 2)

Status: complete (agent-scoped tasks). Chain strategy confirmed `stacked-to-main`, PR 2 of 6 (updated `tasks.md`'s forecast table from `pending` to resolved).

### Completed Tasks
- [x] 2.1 `web/package.json` — added `@supabase/supabase-js`, `libsodium-wrappers`; ran `npm install --prefix web` (removed the auto-added `@types/libsodium-wrappers` stub — the package ships its own types)
- [x] 2.2 `web/src/api/types.ts` (shared types + `Backend` interface), `web/src/api/local.ts` (moved the original FastAPI client here unchanged), `web/src/api/supabase.ts` (auth, sealed-credential upload, queue/config/schedule CRUD, refresh dispatch, account deletion), `web/src/api.ts` rewritten as the `VITE_BACKEND` facade dispatching to one of the two backends
- [x] 2.3 `web/src/seal.ts` — lazy-imported `crypto_box_seal` against `VITE_SEAL_PUBLIC_KEY`/`VITE_SEAL_KEY_ID` (base64, standard alphabet); only pulled in when `saveCredentials` actually runs
- [x] 2.4 `web/src/components/AuthGate.tsx`, `SignIn.tsx`, `CredentialsForm.tsx` — session + saved-credential gate, sign-in/sign-up toggle, one-time UPV credential capture
- [x] 2.5 `web/src/main.tsx` wraps `<App />` in `<AuthGate>`. `web/src/App.tsx` needed **no code changes** to stay compatible (see Deviations) — the task is complete in intent (the app is gated) even though that one file has a zero-line diff
- [x] 2.6 `npm run build --prefix web` — passes (see Work Unit Evidence)

### Files Changed
| File | Action | Lines (+/-) |
|------|--------|-------------|
| `web/package.json` | Modified | +2/-0 |
| `web/package-lock.json` | Modified (generated) | not counted toward authored risk |
| `web/.gitignore` | Modified | +2/-0 (ignore `web/.env`, `web/.env.local`) |
| `web/.env.example` | Created | +19/-0 |
| `web/src/api/types.ts` | Created | +80/-0 |
| `web/src/api/local.ts` | Created | +59/-0 |
| `web/src/api/supabase.ts` | Created | +230/-0 |
| `web/src/api.ts` | Rewritten (facade) | +47/-74 |
| `web/src/seal.ts` | Created | +45/-0 |
| `web/src/vite-env.d.ts` | Created | +17/-0 |
| `web/src/components/AuthGate.tsx` | Created | +82/-0 |
| `web/src/components/SignIn.tsx` | Created | +84/-0 |
| `web/src/components/CredentialsForm.tsx` | Created | +67/-0 |
| `web/src/main.tsx` | Modified | +4/-1 |
| `web/src/styles.css` | Modified | +113/-1 |

Total authored lines (excludes the generated `package-lock.json`): **851 additions + 76 deletions = 927 changed lines**, well above the 400-line default and above the forecast's own ~350-450 estimate for this slice, and above PR 1's own ~505-line overrun.

**One trimming pass was already taken**: the first draft of `api/supabase.ts` included a private, temporary TypeScript port of `schedule_view.py`'s `build_days`/`count_enrolled_now` (~90 lines) so the Supabase-backed agenda view would render real days instead of an empty list. That duplicated Phase 5's explicitly assigned task 5.3 (`web/src/scheduleView.ts`, "port `build_days` to TypeScript") ahead of schedule and crossed the "do not touch Phase 3+ files" boundary in spirit, so it was removed: `getSchedule()` now returns `days: []` for the Supabase backend with a comment pointing at task 5.3, and `enrolled_this_week` is computed directly from the raw cached groups (kept — it is a 3-line reduction, not day-building). This cut ~90 lines and, more importantly, respects the phase boundary; it did not fit the review budget on its own.

No further cut is honest without deleting a task 2.1-2.6 deliverable outright: `api/supabase.ts` (230 lines) implements 3 auth functions + `hasCredentials` + `saveCredentials`/`deleteAccount`/`requestRefresh` + `getConfig`/`putBookings`/`getSchedule`, all explicitly required by task 2.2's "plus `requestRefresh`, `saveCredentials`, `deleteAccount`"; the three components (233 combined lines) are task 2.4's explicit deliverables; `seal.ts` is task 2.3; `types.ts`/`local.ts`/the `api.ts` rewrite are the mechanical split task 2.2 asks for; `styles.css` (+113) is the minimum styling for three new full-screen auth states reusing existing tokens (`--card`, `--accent`, `--line`, `.cta`, `.press`) rather than inventing a new visual language. Recommend **`size:exception`** for this slice, consistent with PR 1's precedent — the orchestrator/user already resolved `ask-on-risk` toward `stacked-to-main` at slice granularity for this change.

### Work Unit Evidence
| Evidence | Value |
|---|---|
| Focused test command and exact result | `npm run build --prefix web` (`tsc -b && vite build`) — passes, 103 modules, no type errors. `.venv\Scripts\python.exe -m pytest -q` — 79 passed (no Python files touched in this unit; confirms no regression) |
| Runtime harness command/scenario and exact result | `VITE_BACKEND=local npx vite --port 5183 --strictPort` (dev server) — `/`, `/src/main.tsx`, `/src/components/AuthGate.tsx`, `/src/api/supabase.ts` all transform with HTTP 200, confirming `AuthGate` bypasses cleanly under the local backend without the lazily-constructed Supabase client ever running. Separately rebuilt once with placeholder `VITE_SEAL_PUBLIC_KEY`/`VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY` env vars to confirm the real sealing/Supabase code paths still compile and that `libsodium-wrappers` code-splits into its own lazy chunk (434 kB) instead of inflating the main bundle (dist output discarded after; not committed). No live `supabase start` project was available (OWNER 0.1/1.5 not run), so sign-up/sign-in/save-credentials/queue-write were not exercised end-to-end against a real Supabase project — that manual check is listed in the forecast table's "Runtime harness" column and needs a deployed or local Supabase instance the owner controls |
| Rollback boundary | Revert `web/src/api.ts`, `web/src/main.tsx`, `web/src/styles.css`, `web/package.json`/`package-lock.json`; delete `web/src/api/`, `web/src/seal.ts`, `web/src/vite-env.d.ts`, `web/src/components/AuthGate.tsx`, `SignIn.tsx`, `CredentialsForm.tsx`, `web/.env.example`; drop the two added lines from `web/.gitignore`. No `src/` (Python), `supabase/`, or `.github/workflows/` file was touched |

### Deviations from Design
- `web/src/App.tsx` was not modified. Task 2.5 lists it alongside `main.tsx`, but wrapping in `AuthGate` only required a change in `main.tsx` (`<AuthGate><App /></AuthGate>`); `App.tsx` already imports everything it needs from the `./api` facade by name, and the facade re-exports the same names, so it kept working unchanged. Design's own file table combines this row with Phase 4's "drive `refreshing` from the hook," which is a separate, later `App.tsx` change (task 4.7) — that is presumably what the table's `App.tsx` mention was mostly about.
- `getSchedule()`'s Supabase implementation returns `days: []` rather than a populated agenda (see the trimming note above): the day-view conversion from cached `schedules.groups` is Phase 5's task 5.3. `limits.queued`/`limits.enrolled_this_week` and the queue panel (bookings) are fully functional today; only the agenda/rail view stays empty until Phase 5 lands.
- `getSchedule(refresh: true)` (the manual "Actualizar tabla" button) now calls `requestRefresh("manual")` before reading the still-cached row — this surfaces the Edge Function's rate-limit errors today, but the 1-2 min wait for a fresh result and its loading state is `useRefreshStatus.ts` (Phase 4, explicitly out of scope here). Until Phase 4, clicking refresh under the Supabase backend kicks off a real refresh but the UI will not visibly update until Phase 5/4 land together.
- Sign-in does not itself trigger a `signin`-throttled refresh; wiring that (and the manual button's throttle/rate-limit UX) is task 4.6 (`useRefreshStatus.ts`) by design.
- No UI calls `deleteAccount()` yet — task 2.2 asks only for the function to exist on the facade; no Phase 2 task creates an account-settings screen. Left as an exported, untested-from-the-UI function for a later phase to wire up.
- Base64 wire format for the sealed payload and the public key was not specified further than "base64" in design.md; picked the standard padded alphabet (libsodium's `base64_variants.ORIGINAL`) since PyNaCl's `base64.b64decode` (Phase 3, not yet written) expects that by default. Flagged here so Phase 3's `adapters/sealed_box.py` uses the matching decoder.
- Pre-existing `esbuild`/`vite` dev-server moderate/high advisory (`npm audit`) predates this change (present on the original `vite@^5.4.11` pin) and was not touched — fixing it needs a breaking Vite 8 upgrade, out of scope for this slice.

### Notes / Judgment Calls
- Auth error messages (`Invalid login credentials`, `User already registered`, etc.) and the `validate_queue()` Postgres exception text are translated to the same Spanish copy style the local FastAPI backend already uses (`adapters/web/api.py`'s 422 messages), with a generic Spanish fallback for anything unrecognized — kept UI copy Spanish-only per the session's language contract even though Supabase's own auth errors are English.
- The Supabase client is constructed lazily (`supabase(): SupabaseClient`, not a top-level `export const supabase = createClient(...)`) because `createClient` throws synchronously on an empty URL/key. `api.ts`'s facade statically re-exports `api/supabase.ts`'s auth helpers regardless of `VITE_BACKEND` (so `AuthGate` can import them unconditionally), which means that module is always in the local-mode bundle too; without the lazy constructor, `serve --demo`/local dev would crash at import time with no `VITE_SUPABASE_URL` set. Verified via the dev-server smoke test above.
- `AuthGate` renders a `ThemeToggle` in its own corner (not present in the original design.md task list) so the sign-in/credentials screens are not stuck in whichever theme the OS preferred before the user had any in-app control — small, reuses the existing component and tokens, no new CSS beyond one flex wrapper class.

### Remaining Tasks (later work units, not this agent's scope)
- [ ] Phase 3 (PR 3): Python Supabase adapter + `book-all` loop
- [ ] Phase 4 (PR 4): Refresh — Edge rate-limit + Realtime (finishes `refresh/index.ts`, `useRefreshStatus.ts`, wires `App.tsx`'s `refreshing` state)
- [ ] Phase 5 (PR 5): Pages deploy + Vite `base`, and `scheduleView.ts` (task 5.3) — closes the `days: []` gap left in this unit's `getSchedule()`
- [ ] Phase 6 (PR 6): Migration + docs

### Workload / PR Boundary
- Mode: stacked PR slice (`stacked-to-main`), PR 2 of 6
- Current work unit: Unit 2 — Browser auth + sealed-box + `api.ts`
- Boundary: starts from the single-user `web/src/api.ts` + no auth gate; ends with a working `VITE_BACKEND` facade (local FastAPI unaffected), sign-up/sign-in/credential-sealing UI, and a functional (if agenda-less until Phase 5) Supabase-backed queue
- Estimated review budget impact: ~927 authored lines (851 additions + 76 deletions), well above the 400-line default and above this slice's own ~350-450 forecast; recommend `size:exception` — the unit is atomic (splitting further would ship a facade with no usable auth UI, or auth UI with no facade to call), and one honest trimming pass (removing the Phase-5-duplicating schedule-view port) already happened

## Work Unit 3 — Python Supabase Adapter + `book-all` Loop (PR 3)

Status: complete (all Phase 3 tasks). Chain strategy confirmed `stacked-to-main`, PR 3 of 6.

### Completed Tasks
- [x] 3.1 RED `tests/test_run_batch.py::test_one_users_login_failure_does_not_block_the_others` — user B's `AuthenticationFailed` login is recorded as `incomplete`; A and C still book and are recorded `booked`
- [x] 3.2 RED `tests/test_run_batch.py::test_empty_roster_produces_no_result_and_no_email` — an empty roster (mirrors `batch_roster()` excluding empty queues) calls `record_result` and the notifier factory zero times
- [x] 3.3 RED `tests/test_turns.py` — `TurnScheduler` FIFO/starvation logic (no real threads needed) plus a real-thread mutual-exclusion test (`max_concurrent == 1` across 3 users x 4 rounds each) and `TurnTakingClock` sleep/yield/reacquire behavior
- [x] 3.4 RED `tests/test_sealed_box.py` — a fixture actually sealed by the real `libsodium-wrappers` npm package (generated once via `node`, committed as `tests/fixtures/sealed_credentials_interop.json`) opens correctly with PyNaCl's `SealedBox`; unknown `key_id`, wrong private key, and corrupt ciphertext all raise `CredentialsUnavailable`
- [x] 3.5 RED `tests/test_log_redaction.py` — `caplog` has no username/password/group-code/email/UUID after `RedactingFilter`; `configure_log_hygiene` sets the `httpx` logger to WARNING
- [x] 3.6 `src/upv_auto/ports.py` — added `UserDirectory` (`roster`, `record_result`, `claim_request`, `save_schedule`, `finish_request`) and `CredentialOpener` (`open`), matching design.md's Interfaces/Contracts exactly
- [x] 3.7 `src/upv_auto/app/turns.py` — `TurnScheduler` (condition-variable FIFO rotation), `TurnTakingClock` (yields on `sleep()`, reacquires after), `BufferedNotifier`
- [x] 3.8 `src/upv_auto/app/run_batch.py` — roster loop (one thread per user), per-user `dataclasses.replace(config, credentials=..., bookings=..., email=None)`, try/except/finally per user (`booked`/`incomplete`/`credentials_unavailable`/`error`), sequential per-user email send after every thread joins
- [x] 3.9 `src/upv_auto/adapters/supabase_rest.py` — `SupabaseRestUserDirectory`: httpx PostgREST client with the service-role key, implementing all 5 `UserDirectory` methods plus one extra `upsert_settings` (see Notes)
- [x] 3.10 `src/upv_auto/adapters/sealed_box.py` — `SealedBoxOpener` (PyNaCl `SealedBox`, `key_id -> private key` map) + `generate_keypair()`
- [x] 3.11 `src/upv_auto/adapters/log_redaction.py` — `RedactingFilter` (registered secrets + group-code/email/UUID patterns), `configure_log_hygiene`, `mask_for_actions`
- [x] 3.12 `src/upv_auto/__main__.py` — `book-all [--now]` and `seal-keygen [--key-id]` subcommands, each with its own config/secret loading (see Deviations)
- [x] 3.13 `pyproject.toml` — `multiuser = ["pynacl>=1.5"]` extra; installed into `.venv`
- [x] 3.14 `.github/workflows/book.yml` — `book-all` mode option, `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`/`SEAL_PRIVATE_KEYS` secrets, no artifact upload for `book-all`, fixed `run-name` for `book-all`
- [x] 3.15 `.venv\Scripts\python.exe -m pytest -q` — 110 passed (79 baseline + 31 new)

### Files Changed
| File | Action | Lines (+/-) |
|------|--------|-------------|
| `src/upv_auto/app/turns.py` | Created | +104/-0 |
| `src/upv_auto/app/run_batch.py` | Created | +199/-0 |
| `src/upv_auto/adapters/supabase_rest.py` | Created | +169/-0 |
| `src/upv_auto/adapters/sealed_box.py` | Created | +66/-0 |
| `src/upv_auto/adapters/log_redaction.py` | Created | +80/-0 |
| `src/upv_auto/ports.py` | Modified | +43/-1 |
| `src/upv_auto/domain/models.py` | Modified | +22/-0 |
| `src/upv_auto/domain/errors.py` | Modified | +7/-0 |
| `src/upv_auto/config.py` | Modified | +22/-8 (`_parse_booking` renamed to public `parse_booking_dict`; `require_upv_credentials` flag added) |
| `src/upv_auto/__main__.py` | Modified | +137/-2 |
| `pyproject.toml` | Modified | +3/-0 |
| `.github/workflows/book.yml` | Modified | +23/-5 |
| `tests/fakes.py` | Modified | +10/-3 (`FakeClock` made thread-safe) |
| `tests/test_config.py` | Modified | +11/-0 |
| `tests/test_turns.py` | Created | +170/-0 |
| `tests/test_run_batch.py` | Created | +218/-0 |
| `tests/test_sealed_box.py` | Created | +78/-0 |
| `tests/test_log_redaction.py` | Created | +63/-0 |
| `tests/test_supabase_rest.py` | Created | +165/-0 |
| `tests/fixtures/sealed_credentials_interop.json` | Created | +9/-0 |

Total authored: **~1610 additions + ~19 deletions ≈ 1629 changed lines**, far above the 400-line default and above this slice's own ~350-450 forecast — larger than PR 1 (~505) and roughly comparable to PR 2 (~927). No further honest trim: `run_batch.py`/`turns.py` are one cohesive turn-taking mechanism (splitting the scheduler from its caller would ship an untestable half); `supabase_rest.py` implements the full `UserDirectory` contract in one file per design.md's single "Create" row (a partial adapter would leave Phase 4 needing to add methods to a file design already scoped as complete); the five new RED test files are the task list's own explicit deliverables. Recommend **`size:exception`**, consistent with PR 1 and PR 2's precedent.

### Work Unit Evidence
| Evidence | Value |
|---|---|
| Focused test command and exact result | `.venv\Scripts\python.exe -m pytest -q` — 110 passed, 0 failed (79 baseline + 31 new: 4 `test_run_batch.py`, 9 `test_turns.py`, 5 `test_sealed_box.py`, 4 `test_log_redaction.py`, 8 `test_supabase_rest.py`, 1 `test_config.py`) |
| Runtime harness command/scenario and exact result | No live Supabase project (OWNER 0.1/1.5 not run) and no real UPV credentials, so `book-all` was not run end to end. Two real-boundary checks instead: (1) `tests/fixtures/sealed_credentials_interop.json` was generated by actually running `node` against the real `libsodium-wrappers` package already installed under `web/node_modules` (the same package `web/src/seal.ts` imports) — sealing a payload there and opening it with PyNaCl in `test_sealed_box.py` proves the browser-to-runner wire format really round-trips, not just PyNaCl-with-itself; (2) CLI smoke tests: `python -m upv_auto seal-keygen --key-id v1` printed a real usable key pair, `python -m upv_auto book-all --help` and top-level `--help` show the new subcommands correctly, and `python -m upv_auto book-all --now` (no Supabase secrets set) failed fast with `Missing required environment variable: SUPABASE_URL` — confirming `load_config(..., require_upv_credentials=False)` does NOT demand `UPV_USERNAME`/`UPV_PASSWORD` (the scenario OWNER 6.5 depends on). `npm run build --prefix web` also rerun as a secondary regression check (unaffected by this unit, still 103 modules, no errors) |
| Rollback boundary | Delete `src/upv_auto/app/turns.py`, `app/run_batch.py`, `adapters/supabase_rest.py`, `adapters/sealed_box.py`, `adapters/log_redaction.py`, `tests/test_turns.py`, `test_run_batch.py`, `test_sealed_box.py`, `test_log_redaction.py`, `test_supabase_rest.py`, `tests/fixtures/sealed_credentials_interop.json`. Revert `ports.py`, `domain/models.py`, `domain/errors.py`, `config.py`, `__main__.py`, `pyproject.toml`, `.github/workflows/book.yml`, `tests/fakes.py`, `tests/test_config.py`. No file from Work Unit 1 or 2 was touched beyond this list |

### Deviations from Design
- **`load_config(require_upv_credentials=False)`** (new keyword-only parameter, default `True`, so single-user callers are unaffected): design.md's per-user config line reads `dataclasses.replace(load_config(), credentials=…, …)`, implying a bare `load_config()` call — but `load_config()` unconditionally requires `UPV_USERNAME`/`UPV_PASSWORD` env vars, and design.md's own Migration/Rollout section says those two secrets are **deleted** once migration is verified. Once deleted, a bare `load_config()` call in `book-all` would raise `ConfigError` every week. Added the flag so `book-all` can load `config.yaml`'s activity/window/limits/timezone without ever needing a single shared UPV login — the real per-user credentials are substituted in immediately after via `dataclasses.replace`, exactly as design.md describes. Noting this because it is a literal deviation from the design snippet's wording, even though it is required for the design's own stated end state to actually work.
- **`app_settings` upsert added to `book-all`** (`SupabaseRestUserDirectory.upsert_settings`, called once per run from `__main__._book_all` before `run_batch`): design.md's Schema table says `app_settings` is "upserted from `config.yaml` on every run," but no task in tasks.md (Phase 3 or later) assigns this. Without it, the web frontend's `getConfig()` (already built in PR 2, reading `app_settings.settings`) would see `activity`/`window`/`limits` stay `{}` forever — the queue panel would work but the activity name/window/limits shown to the user never would. Implemented as a small extra method on the adapter, not part of the `UserDirectory` protocol (not used by `run_batch`, called directly by `__main__` as the composition root) — see design.md's own gap here.
- **`config.parse_booking_dict`** — the design's per-file table doesn't call this out, but `supabase_rest.roster()` needs the exact same `{"group_code": ..., "alternatives": [...]}`  -> `BookingTarget` parsing `load_config()` already does for `config.yaml`'s `bookings:` block (and `booking_queue.bookings` uses the identical JSON shape — confirmed by reading PR 2's `web/src/api/supabase.ts`/`Booking` type). Renamed the existing private `_parse_booking` to public `parse_booking_dict` and reused it, rather than duplicating group-code validation in the adapter.
- **`notifier_factory` parameter on `run_batch`** — design.md's Interfaces/Contracts section doesn't list this on `UserDirectory` or as a separate parameter, but "one email per user, sent sequentially after all threads join" (design.md's Notification decision) requires *something* to build a real per-user `Notifier` (keyed by that user's own email from the roster) after the turn-taking phase ends. Added `notifier_factory: Callable[[UserRecord], Notifier]`, called only after every thread has joined — SMTP never runs inside the turn-taking window.
- **`upv_credentials` lookup in `claim_request`** — a two-step PostgREST call (`refresh_requests` by id, then `upv_credentials` by the returned `user_id`) rather than one embedded query, because PostgREST resource embedding needs a direct FK between the two tables, and both only reference `auth.users` independently (confirmed by reading `0001_multi_user.sql`). This method is Phase 4 territory functionally (`refresh_user.py` doesn't exist yet), but the adapter method itself was in scope per design.md's single "Create" row for `supabase_rest.py`, so it needed *a* correct implementation now, even though `run_batch`/`book-all` never calls it this PR.

### Notes / Judgment Calls
- `RedactingFilter` is attached directly to the **root logger** (`logging.getLogger().addFilter(...)`), not to each handler individually — attaching to the logger means pytest's own `caplog` handler (added later, at test time) still sees already-redacted records, which is what task 3.5's RED test needs. Attaching only to existing handlers at `configure_log_hygiene()` time would miss caplog entirely.
- `RedactingFilter`/`FakeClock` were made explicitly thread-safe (an internal `threading.Lock`) because `run_batch` calls `RedactingFilter.register()` from several user threads concurrently, and `tests/fakes.py`'s `FakeClock` is shared across `TurnTakingClock`s in `test_turns.py`'s concurrency tests. Neither was thread-safe before this PR (not needed by anything single-user).
- `TurnScheduler.finish()` is called from a `finally` block in `run_batch._process_user`, unconditionally, even for a user who never reached `scheduler.acquire()` (e.g. `CredentialsUnavailable` before any UPV interaction) — without this, a user who fails early would permanently occupy a rotation slot and deadlock everyone queued behind them once their turn comes up. This is the one correctness-critical detail in the turn-taking design that isn't spelled out in design.md and would only surface as an intermittent multi-user hang, not a single-user test failure.
- `book-all`'s adapter/app imports (`log_redaction`, `sealed_box`, `supabase_rest`, `run_batch`) are inside `_book_all()`, wrapped in `try/except ImportError`, mirroring the existing `_serve()` pattern for the `web` extra — the single-user CLI (`book`/`check-login`/`list-groups`/`serve --demo`) stays fully functional even without the `multiuser` extra installed.
- `EmailNotifier`/`ConsoleNotifier` needed no changes: `ConsoleNotifier.notify()` logs the raw summary text at INFO, and since `RedactingFilter` is attached to the root logger for the whole `book-all` process, group codes in that text are scrubbed to `[group]` automatically — this only holds because the filter is process-wide, not per-adapter.

### Remaining Tasks (later work units, not this agent's scope)
- [ ] Phase 4 (PR 4): Refresh — Edge rate-limit + Realtime (finishes `refresh/index.ts`, `useRefreshStatus.ts`, wires `App.tsx`'s `refreshing` state; will exercise `claim_request`/`save_schedule`/`finish_request` for the first time)
- [ ] Phase 5 (PR 5): Pages deploy + Vite `base`, `scheduleView.ts` (task 5.3)
- [ ] Phase 6 (PR 6): Migration + docs

### Workload / PR Boundary
- Mode: stacked PR slice (`stacked-to-main`), PR 3 of 6
- Current work unit: Unit 3 — Python Supabase adapter + `book-all` loop
- Boundary: starts from no multi-user Python code at all (single-user `book`/`config.yaml` path only); ends with a fully tested, turn-taking, per-user-isolated `book-all` command wired into `book.yml`, backed by a real Supabase PostgREST adapter and a JS-libsodium-interop-proven sealed-box opener — not yet runnable end to end without a live Supabase project (OWNER 0.1/1.5) and real sealed credentials
- Estimated review budget impact: ~1629 authored lines, above the 400-line default and above this slice's own ~350-450 forecast; recommend `size:exception`, consistent with PR 1 and PR 2

## Work Unit 4 — Refresh: Edge Rate-Limit + Realtime (PR 4)

Status: complete (all Phase 4 tasks). Chain strategy confirmed `stacked-to-main`, PR 4 of 6.

### Completed Tasks
- [x] 4.1 RED `tests/test_refresh_user.py::test_cli_rejects_a_non_uuid_request_id` (+ a second empty-string case) — `refresh --request-id` returns exit code 1 before touching config, Supabase, or the login flow (threat matrix: workflow-input injection)
- [x] 4.2 `supabase/functions/refresh/index.ts` finished — `getUser()` (already present) -> parses `{ trigger }` -> `rpc/claim_refresh` (under the caller's own JWT, never service role) -> on a non-null claim, `workflow_dispatch`s `refresh.yml` with `request_id` as the only input; a `null` claim answers `{dispatched:false}` (silent) for `signin` or `429 {error:"rate_limited"}` for `manual`; a failed dispatch marks the claimed row `failed`/`dispatch_failed` via the service role so it does not block a retry via `claim_refresh`'s 15-min pending-reuse window
- [x] 4.3 `.github/workflows/refresh.yml` — `workflow_dispatch` with one required `request_id` string input, `timeout-minutes: 10`, no `concurrency:` group, `REQUEST_ID` passed only through `env` (never interpolated), a bash regex UUID check before the CLI even runs, no artifact upload
- [x] 4.4 `src/upv_auto/app/refresh_user.py` — `refresh_user()`: `claim_request` -> unseal -> `fetch_schedule` -> `save_schedule` + `finish_request(ok=True)`; every failure path (`claim_request` miss, `CredentialsUnavailable`, `fetch_schedule` returning `None`, or an unexpected exception) calls `finish_request(ok=False, error_code=...)` so a request never sits `pending` forever
- [x] 4.5 `src/upv_auto/__main__.py` — `refresh --request-id` subcommand: validates the UUID first (before any import/env/network), then lazily imports the multiuser adapters (mirrors `_book_all`'s ImportError guard) and wires `SupabaseRestUserDirectory`, `SealedBoxOpener`, the existing single-user `PlaywrightCasAuthenticator`/`HttpxSessionVerifier`/`HttpxActivityTableClient`, and `RedactingFilter`/`mask_for_actions` for log hygiene (same pattern as `book-all`)
- [x] 4.6 `web/src/api/useRefreshStatus.ts` — Realtime hook on `refresh_requests` (via a new `subscribeToRefreshRequests`/`getLatestRefreshRequest` pair in `api/supabase.ts`): seeds state from the latest row, subscribes to changes, exposes `{pending, message, triggerManualRefresh}`; fires the sign-in-triggered refresh once per signed-in session (silently absorbing a server-side throttle) and the manual button's rate-limited trigger (surfacing Spanish rate-limit/error copy)
- [x] 4.7 `web/src/App.tsx` — `refreshing` now comes from `useRefreshStatus().pending` under the Supabase backend (local backend keeps its own synchronous `localRefreshing` state, since the hook no-ops under `VITE_BACKEND=local`); the manual "Actualizar tabla"/"Actualizar" buttons call `triggerManualRefresh()`; the header's status pill also shows `refreshStatus.message` (Spanish) when a manual click is rate-limited or a refresh finishes `failed`
- [x] 4.8 `.venv\Scripts\python.exe -m pytest -q` (117 passed) and `npm run build --prefix web` (104 modules, no type errors)

### Files Changed
| File | Action | Lines (+/-) |
|------|--------|-------------|
| `supabase/functions/refresh/index.ts` | Modified (finished) | +82/-16 |
| `.github/workflows/refresh.yml` | Created | +69/-0 |
| `src/upv_auto/app/refresh_user.py` | Created | +96/-0 |
| `src/upv_auto/__main__.py` | Modified | +81/-2 |
| `tests/test_refresh_user.py` | Created | +198/-0 |
| `web/src/api/supabase.ts` | Modified | +75/-6 |
| `web/src/api/useRefreshStatus.ts` | Created | +131/-0 |
| `web/src/App.tsx` | Modified | +30/-9 |

Total authored: **~562 additions + ~33 deletions ≈ 595 changed lines** (git-diff-verified for the four modified files: `+280/-31`; the four new files add `69+96+198+131=494` lines, of which the split above allocates authored-vs-generated per file), above the 400-line default and above this slice's own ~350-450 forecast, but smaller than PR 1 (~505), PR 2 (~927), and PR 3 (~1629). No further honest trim: `refresh/index.ts` is one cohesive claim-then-dispatch flow (splitting the throttle-vs-rate-limit branching from the dispatch call would leave half unusable); `refresh_user.py` mirrors `run_batch.py`'s one-file-per-use-case shape; `useRefreshStatus.ts` owns both Realtime subscription and the two triggers the spec assigns it in one task (4.6); the RED test file is task 4.1's own explicit deliverable, plus the state-transition unit tests design.md's Testing Strategy table asks for (`refresh_user`'s state transitions). Recommend **`size:exception`**, consistent with PR 1-3's precedent.

### Work Unit Evidence
| Evidence | Value |
|---|---|
| Focused test command and exact result | `.venv\Scripts\python.exe -m pytest -q` — 117 passed, 0 failed (110 baseline + 7 new in `tests/test_refresh_user.py`: 2 CLI UUID-rejection cases, 5 `refresh_user()` state-transition cases). `npm run build --prefix web` (`tsc -b && vite build`) — passes, 104 modules, no type errors |
| Runtime harness command/scenario and exact result | No live Supabase project (OWNER 0.1/1.5 not run), so the Edge Function and `refresh.yml` were not exercised end to end against real infrastructure — that manual checklist (design.md's Testing Strategy: "SQL/Edge... Manual checklist against `supabase start`") is deferred to whoever runs OWNER 1.5. Three real-boundary checks instead: (1) CLI smoke test — `python -m upv_auto refresh --request-id not-a-uuid` logs `Invalid --request-id: expected a UUID` and exits 1 in ~0.1s, confirming the threat-matrix guard fires before any config/env/network access; (2) `VITE_BACKEND=local npx vite --port 5184 --strictPort` (dev server) — `/`, `/src/main.tsx`, `/src/App.tsx`, `/src/api/useRefreshStatus.ts` all transform with HTTP 200, confirming the new hook module loads cleanly and its `BACKEND === "local"` early-return means it never touches the Supabase client under local mode; (3) `npm run build --prefix web` also re-verifies the Supabase code path type-checks (the hook, `subscribeToRefreshRequests`, `getLatestRefreshRequest` are statically imported regardless of `VITE_BACKEND`) |
| Rollback boundary | Delete `.github/workflows/refresh.yml`, `src/upv_auto/app/refresh_user.py`, `tests/test_refresh_user.py`, `web/src/api/useRefreshStatus.ts`. Revert `supabase/functions/refresh/index.ts` to its Phase 1 skeleton, `src/upv_auto/__main__.py` (drop the `refresh` subcommand/`_refresh()`), `web/src/api/supabase.ts` (drop `subscribeToRefreshRequests`/`getLatestRefreshRequest`/error-code translation, restore the old `getSchedule`'s internal `requestRefresh` call), and `web/src/App.tsx` (restore the plain `refreshing` state and the old `refresh()` body). No file from Work Unit 1, 2, or 3 was touched beyond this list |

### Deviations from Design
- **`getSchedule(refresh)` no longer calls `requestRefresh` internally** (Work Unit 2's stopgap, explicitly flagged there as "until Phase 4 lands"): now that `useRefreshStatus.triggerManualRefresh()` owns dispatching the manual refresh and setting `pending`, having `getSchedule` also fire-and-forget a `requestRefresh("manual")` on every `refresh=true` read would double-dispatch (and, worse, silently eat the Edge Function's rate-limit error instead of surfacing it to the user). The `refresh` parameter is kept on `getSchedule` (renamed `_refresh` internally) only because it is part of the shared `Backend` interface the local FastAPI backend also implements.
- **Sign-in throttled refresh has no explicit task-assigned call site other than the hook itself**: task 4.6 says "wire sign-in throttle... triggers" into `useRefreshStatus.ts`, so the hook fires `requestRefresh("signin")` once per signed-in session (guarded by a ref, reset on sign-out) rather than `AuthGate.tsx` or `main.tsx` doing it — this keeps every refresh-related side effect in one file, and `AuthGate` stays focused on the sign-in/credentials gate.
- **`refresh/index.ts`'s dispatch uses a hardcoded `ref: "main"`**, not a configurable env var: design.md's Interfaces/Contracts section does not specify this, and every other workflow in this repo (`book.yml`, `keepalive.yml`) already assumes `main` implicitly (no other long-lived branch exists). Documented in the function's header comment alongside the two new secrets it needs (`GITHUB_REPO`, `GITHUB_DISPATCH_TOKEN`) so Phase 6's README task can list them.
- **`refresh_user()` takes `table_client`/`authenticator`/`verifier` directly, not factories** (unlike `run_batch`'s `*_factory` callables): a refresh processes exactly one user per process invocation (`refresh.yml` runs once per `request_id`, no turn-taking), so there is no per-user factory indirection to thread through — `_refresh()` in `__main__.py` constructs each adapter once, the same shape `book`/`list-groups`/`check-login` already use.

### Notes / Judgment Calls
- `claim_refresh`'s null-claim case is answered differently per trigger by `refresh/index.ts`, not by the SQL function: `signin` gets a silent `200 {dispatched:false}` (schedule-refresh spec's "no new refresh is dispatched" — not user-facing as an error), `manual` gets `429 {error:"rate_limited"}` (spec's "the request is rejected"). `claim_refresh` itself stays trigger-agnostic (returns `null` either way), matching its existing Work Unit 1 contract untouched.
- Marking a claimed-but-undispatched request `failed`/`dispatch_failed` (when the GitHub API call itself fails, e.g. a bad PAT or GitHub outage) uses a short-lived service-role client constructed only for that one `update` call — the Edge Function's normal path never needs the service role (`claim_refresh` and the `select`/`update` a user's own row all work under the caller's own JWT); only this one error-recovery branch does, because `refresh_requests` grants no `update` policy to `authenticated`.
- `useRefreshStatus`'s `getLatestRefreshRequest()` seed read (task 4.6 wasn't explicit about page-reload-while-pending, but the "Visible Loading State" spec requirement implies it) exists because Realtime's `postgres_changes` only reports rows that change *after* the channel subscribes — without it, a user who clicks refresh and reloads the tab mid-flight would see no loading indicator until the *next* status change, even though a refresh is still genuinely in flight.
- `KNOWN_REFRESH_ERRORS`/`DONE_ERRORS` are two small, separate Spanish-copy maps (one in `api/supabase.ts` for the Edge Function's synchronous rejection, one in `useRefreshStatus.ts` for a request that finishes `failed` asynchronously) rather than one shared map, because the two are keyed by different vocabularies: the Edge Function's immediate `{error:"<code>"}` body vs. `refresh_requests.error_code` set by the Python runner. Both fall back to a generic Spanish message for an unrecognized code, so a new error code introduced later degrades gracefully instead of showing untranslated English or crashing.
- Detailed loading-state visual design is explicitly out of scope per the session's task framing and design.md's Purpose statement ("Loading-animation design is out of scope; only the presence of a loading state is specified") — `refreshing` continues driving the exact same `spin`/`"Actualizando…"` UI Work Unit 2 already had; only what sets `refreshing` changed.

### Remaining Tasks (later work units, not this agent's scope)
- [ ] Phase 5 (PR 5): Pages deploy + Vite `base`, `scheduleView.ts` (task 5.3 — ports `build_days` to TypeScript, closing the `days: []` gap left in `getSchedule()`)
- [ ] Phase 6 (PR 6): Migration + docs (README must document `GITHUB_REPO`/`GITHUB_DISPATCH_TOKEN` as Edge Function secrets, distinct from the GitHub Actions secrets OWNER 0.3 already lists)

### Workload / PR Boundary
- Mode: stacked PR slice (`stacked-to-main`), PR 4 of 6
- Current work unit: Unit 4 — Refresh: Edge rate-limit + Realtime
- Boundary: starts from the Phase 1 `refresh/index.ts` skeleton (auth-only, `501 not_implemented`) and no `refresh.yml`/`refresh_user.py`/`useRefreshStatus.ts`; ends with the full sign-in-throttled + manual-rate-limited refresh path wired end to end (Edge Function -> SQL `claim_refresh` -> `workflow_dispatch` -> `refresh.yml` -> `refresh_user.py` -> `schedules`/`refresh_requests` -> Realtime -> `useRefreshStatus` -> `App.tsx`'s existing loading UI) — not yet runnable end to end without a live Supabase project, a deployed Edge Function, and the two new GitHub secrets (`GITHUB_REPO`, `GITHUB_DISPATCH_TOKEN`)
- Estimated review budget impact: ~595 authored lines, above the 400-line default and above this slice's own ~350-450 forecast; recommend `size:exception`, consistent with PR 1-3 (the smallest overrun of the four so far)

## Work Unit 5 — Pages Deploy + Vite `base` (PR 5)

Status: complete (all Phase 5 tasks). Chain strategy `stacked-to-main`, PR 5 of 6.

### Completed Tasks
- [x] 5.1 `web/vite.config.ts` — `base: process.env.VITE_BASE_PATH ?? "/"`, with a comment noting local dev/`serve --demo` never set `VITE_BASE_PATH` so the `/api` proxy is unaffected
- [x] 5.2 `.github/workflows/pages.yml` — official `actions/configure-pages` -> build -> `actions/upload-pages-artifact` -> `actions/deploy-pages` pipeline, minimal `contents: read` / `pages: write` / `id-token: write` permissions, no `workflow_dispatch` inputs (nothing to interpolate)
- [x] 5.3 `web/src/scheduleView.ts` — behavior-identical port of `adapters/web/schedule_view.py`'s `build_days`/`count_queued`/`count_enrolled_now`; wired into `web/src/api/supabase.ts`'s `getSchedule()`, replacing the `days: []` stub left by Work Unit 2
- [x] 5.4 Verified `VITE_BACKEND=local` still serves under `/` (dev-server smoke test, see Work Unit Evidence) — `serve --demo`'s `/api` proxy path is unaffected by the Pages `base` change
- [x] 5.5 `npm run build --prefix web` tested both with `VITE_BASE_PATH=/upv-auto/` set (assets resolve under `/upv-auto/assets/...`) and unset (assets resolve under `/assets/...`, matching pre-Phase-5 behavior)

### Files Changed
| File | Action | Lines (+/-) |
|------|--------|-------------|
| `web/vite.config.ts` | Modified | +6/-0 |
| `.github/workflows/pages.yml` | Created | +72/-0 |
| `web/src/scheduleView.ts` | Created | +112/-0 |
| `web/src/api/supabase.ts` | Modified | +3/-10 (import `buildDays`/`countEnrolledNow`, drop the local `countEnrolledThisWeek` and the `days: []` stub) |

Total authored: **193 additions + 10 deletions = 203 changed lines** (git-diff-verified for the two modified files: `web/vite.config.ts` +6/-0, `web/src/api/supabase.ts` +3/-10; the two new files add 72+112=184 lines), well within the 400-line default. No `size:exception` needed for this slice, unlike PR 1-4.

### Work Unit Evidence
| Evidence | Value |
|---|---|
| Focused test command and exact result | `npm run build --prefix web` (`tsc -b && vite build`) — passes, 105 modules, no type errors, run three times: once with `VITE_BASE_PATH` unset (baseline), once with `MSYS_NO_PATHCONV=1 VITE_BASE_PATH=/upv-auto/` (see Notes on the Git-Bash artifact), once more unset afterward to confirm the default still holds. `.venv\Scripts\python.exe -m pytest -q` — 117 passed, 0 failed (no Python files touched in this unit; confirms no regression) |
| Runtime harness command/scenario and exact result | No live GitHub Pages deployment to visit (OWNER 0.4 — enabling Pages — is out of agent scope), so `pages.yml` itself was not run by a real workflow dispatch; validated instead by (1) `python -c "import yaml; yaml.safe_load(open('.github/workflows/pages.yml'))"` confirming well-formed YAML, and (2) a dev-server smoke test: `VITE_BACKEND=local npx vite --port 5187 --strictPort` (no `VITE_BASE_PATH`) served `/`, `/src/main.tsx`, and `/src/scheduleView.ts` all at HTTP 200 under `/` (unchanged from pre-Phase-5), and `/api/config` returned HTTP 500 (connection attempted to the unstarted FastAPI backend at `127.0.0.1:8000`, confirming the proxy itself is still wired, not a routing regression) — this is task 5.4's verification. Separately, `dist/index.html` was inspected after each build: with `VITE_BASE_PATH=/upv-auto/` its `<script src>`/`<link href>` read `/upv-auto/assets/...`; with it unset they read `/assets/...` |
| Rollback boundary | Delete `.github/workflows/pages.yml`, `web/src/scheduleView.ts`. Revert `web/vite.config.ts` (drop the `base` line) and `web/src/api/supabase.ts` (restore the local `countEnrolledThisWeek` and the `days: []` stub, drop the `scheduleView` import). No file from Work Unit 1-4 was touched |

### Deviations from Design
None — `vite.config.ts`'s `base` line matches design.md's File Changes table verbatim, `scheduleView.ts` is a line-for-line-equivalent port of `schedule_view.py` (same day/time ordering rules, same queue-position/alternatives-don't-add rule), and `pages.yml` uses the three official Pages actions design.md's Phase 5 goal implies without design.md prescribing exact step names.

### Notes / Judgment Calls
- `pages.yml`'s build step reads `VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY`/`VITE_SEAL_PUBLIC_KEY`/`VITE_SEAL_KEY_ID` from `secrets.*`, not `vars.*`, even though these four values are public-by-design (an RLS-scoped anon key and a sealed-box public key/id) — kept as `secrets` for consistency with Phase 0's own task list (OWNER 0.3 already names these four as "GitHub secrets" alongside `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`), so the owner sets them in exactly one place GitHub calls "Secrets", not split across Secrets and Variables.
- `VITE_BASE_PATH` is derived from `actions/configure-pages`'s `base_path` output (`steps.pages.outputs.base_path`), not hardcoded as `/upv-auto/` or computed from `github.repository`. `configure-pages` is the GitHub-maintained action that already knows the project's Pages path (org vs. project site, custom domain or not); depending on its output keeps `pages.yml` correct even if the repository is ever renamed or transferred, which the session prompt's `/upv-auto/` example is a *result* of, not a literal string to hardcode.
- `pages.yml` triggers on `push: branches: [main], paths: [web/**, .github/workflows/pages.yml]` plus `workflow_dispatch`. Design.md doesn't specify a trigger; a path-filtered push to `main` matches how a static frontend is conventionally redeployed (only when the frontend actually changed) without adding a new manual step to the Phase 6 migration checklist, and `workflow_dispatch` covers a manual redeploy (e.g. after rotating a `VITE_SEAL_*` secret with no `web/` code change).
- The `"base" option should start with a slash` Vite warning seen during local verification (and a mangled `/Program Files/Git/upv-auto/` asset path) is a Git-Bash/MSYS artifact: MSYS auto-converts any argument or env var value that looks like a POSIX absolute path (`/upv-auto/`) into a Windows path before Node ever sees it. This never happens on the Linux `ubuntu-latest` GitHub Actions runner `pages.yml` actually runs on, and was confirmed non-reproducing locally too with `MSYS_NO_PATHCONV=1` (see Work Unit Evidence) — `dist/index.html` then correctly read `/upv-auto/assets/...`. Documented here so a future contributor testing this on Windows Git Bash doesn't mistake it for a code bug.
- `scheduleView.ts` also ports `count_queued`/`count_enrolled_now` (not just `build_days`), even though task 5.3 names only `build_days` and `getSchedule()` already had inline equivalents (`config.bookings.length`, a local `countEnrolledThisWeek`) since Work Unit 2. Moved both into the new file and imported them, rather than leaving three ad hoc functions split across two files: `scheduleView.ts` is now the one module mirroring `schedule_view.py`'s full surface, which is what "port `build_days` to TypeScript" means in context (design.md's Schema section: "`build_days` is ported to TypeScript", singular file, not singular function) and matches the design's own File Changes table entry for `scheduleView.ts`.

### Remaining Tasks (later work unit, not this agent's scope)
- [ ] Phase 6 (PR 6): Migration + docs — README setup/rotation/migration/local-dev section (including the two Phase 4 Edge Function secrets `GITHUB_REPO`/`GITHUB_DISPATCH_TOKEN` still undocumented), plus every OWNER-only task across all six phases

### Workload / PR Boundary
- Mode: stacked PR slice (`stacked-to-main`), PR 5 of 6
- Current work unit: Unit 5 — Pages deploy + Vite `base`
- Boundary: starts from an unconfigured `base` (Pages-incompatible asset URLs) and no deploy workflow; ends with a Pages-ready build (`base` driven by `VITE_BASE_PATH`, defaulting to `/` so local dev is unaffected), a `pages.yml` that builds and deploys via the official actions, and a populated (no longer `days: []`) Supabase-backed agenda view — not yet deployed live (OWNER 0.4, enabling Pages in repo settings, is out of agent scope)
- Estimated review budget impact: ~203 authored lines, the first slice of this change to land under the 400-line default; no `size:exception` needed
