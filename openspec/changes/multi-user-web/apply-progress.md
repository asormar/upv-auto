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
- [ ] Phase 2 (PR 2): Browser auth + sealed-box + `api.ts`
- [ ] Phase 3 (PR 3): Python Supabase adapter + `book-all` loop
- [ ] Phase 4 (PR 4): Refresh — Edge rate-limit + Realtime (finishes `refresh/index.ts`)
- [ ] Phase 5 (PR 5): Pages deploy + Vite `base`
- [ ] Phase 6 (PR 6): Migration + docs

### Workload / PR Boundary
- Mode: stacked PR slice (`stacked-to-main`), PR 1 of 6
- Current work unit: Unit 1 — Schema, RLS, keepalive, Edge skeleton
- Boundary: starts from no `supabase/` directory and no `keepalive.yml`; ends with a complete, deployable (by the owner) schema + two Edge Functions + keepalive workflow, with zero changes to `src/`, `web/`, or `book.yml`
- Estimated review budget impact: ~505 authored lines, above the 400-line default; recommend `size:exception` for this slice given the migration's atomicity, or accept as reported since `ask-on-risk` already resolved the chain strategy at slice granularity
