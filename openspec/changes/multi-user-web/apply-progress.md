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
