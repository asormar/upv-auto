# Verify Report: multi-user-web

**Change**: `multi-user-web`
**Branch**: `feat/multi-user-6-docs` (6 stacked slices on `main`, PR 1-6 complete per `apply-progress.md`)
**Mode**: Full spec-driven verification (proposal/specs/design/tasks/apply-progress all present)
**Verdict**: **PASS WITH WARNINGS**

## Completeness Table

| Phase | Tasks | Status |
|---|---|---|
| Phase 0 (OWNER prerequisites) | 5 | 0/5 checked, all OWNER-only, expected pending (needs live Supabase project, secrets, Pages, cron-job.org) |
| Phase 1 (Schema/RLS/keepalive/Edge skeleton) | 5 | 4/4 non-OWNER checked; OWNER 1.5 (apply migration + deploy) expected pending |
| Phase 2 (Browser auth + sealed-box + api.ts) | 6 | 6/6 checked |
| Phase 3 (Python Supabase adapter + book-all) | 15 | 15/15 checked |
| Phase 4 (Refresh: Edge rate-limit + Realtime) | 8 | 8/8 checked |
| Phase 5 (Pages deploy + Vite base) | 5 | 5/5 checked |
| Phase 6 (Migration + docs) | 5 | 1/1 non-OWNER checked; OWNER 6.2-6.5 expected pending |

Every non-OWNER task is checked complete. All 10 unchecked tasks (OWNER 0.1-0.5, OWNER 1.5, OWNER 6.2-6.5) are external prerequisites requiring a live Supabase project, real secrets, GitHub Pages enablement, and cron-job.org, correctly out of agent scope, not gaps in the implementation.

## Build/Test Evidence

- `.venv\Scripts\python.exe -m pytest -q` result: 117 passed, 0 failed (exit 0)
- `npm run build --prefix web` (`tsc -b && vite build`) result: passes, 105 modules, no type errors (exit 0)
- Re-ran the multi-user-specific subset (`tests/test_turns.py tests/test_sealed_box.py tests/test_log_redaction.py tests/test_supabase_rest.py -v`): 26/26 passed
- `git diff --stat main..HEAD`: 62 files changed, 5433 insertions, 105 deletions across 8 commits

## Spec Compliance Matrix

24 requirements / 37 scenarios counted directly from the specs' Requirement and Scenario headings.

| Capability | Reqs | Scenarios | Status |
|---|---|---|---|
| booking-queue | 4 | 6 | Limits and alternatives-do-not-count: DB trigger `validate_queue()` reviewed, matches spec; UI mirrors it in App.tsx and QueuePanel.tsx. Empty-queue scenario covered at runtime by test_run_batch.py. RLS cross-user isolation and live queue-editing round trip: needs live check |
| credential-custody | 4 | 6 | Browser sealing and runner unsealing interop covered at runtime by test_sealed_box.py using a fixture actually sealed by the real libsodium-wrappers package and opened with PyNaCl. No-plaintext-in-logs covered at runtime by test_log_redaction.py. Key rotation (unknown key_id raises CredentialsUnavailable) covered at runtime. "No other component can unseal" verified by static review: the private key only ever appears in the SEAL_PRIVATE_KEYS GitHub secret |
| platform-operations | 3 | 5 | Pages hosting and keepalive: SQL and workflow YAML statically reviewed, well-formed and correctly scoped; needs live check (no live Pages deployment or Supabase project). Public log hygiene covered at runtime by test_log_redaction.py plus static review of book.yml/refresh.yml/keepalive.yml confirming no username/email/group-code is ever printed directly and all dynamic inputs go through env, with a UUID guard in refresh.yml |
| schedule-refresh | 4 | 7 | Refresh state-transition logic covered at runtime by 5 cases in test_refresh_user.py; CLI UUID rejection covered at runtime (2 cases). Sign-in throttle and manual rate-limit SQL logic in claim_refresh statically reviewed, matches design.md's throttle table; needs live check for atomic behavior under concurrency. Loading-state Realtime wiring in useRefreshStatus.ts statically reviewed |
| user-accounts | 4 | 7 | Sign-up/sign-in delegate to Supabase Auth, correctly wired with Spanish error translation; needs live check since this is Supabase Auth itself, not custom logic. RLS isolation: every per-user table policy reviewed as user_id = auth.uid(); needs live check. Account deletion cascade: every per-user table's FK is on delete cascade referencing auth.users(id), and delete-account/index.ts calls auth.admin.deleteUser; needs live check for the actual cascade |
| weekly-batch-booking | 5 | 6 | Turn-taking, failure isolation, result recording, and per-user email are all covered at runtime: test_run_batch.py's login-failure isolation test, test_turns.py's 9 cases (fair rotation, no-starvation, real-thread mutual exclusion), and per-user notifier assertions. Booking-window timing unchanged is external cron-job.org config (OWNER 0.5); book.yml's default mode and dispatch shape are unchanged other than the added book-all option |

## Correctness / Design Coherence

- design.md's Architecture Decisions table matches the implementation for every row reviewed: turn-taking (TurnScheduler/TurnTakingClock), sealed format (crypto_box_seal plus key_id, base64 ORIGINAL alphabet on both seal.ts and sealed_box.py), rate limiting inside claim_refresh via pg_advisory_xact_lock, no concurrency group on refresh.yml, front backend selection via VITE_BACKEND, account deletion via Edge Function plus cascade FKs.
- scheduleView.ts is a line-for-line-equivalent port of schedule_view.py: same day-order table, same time-rank and queue-position logic, same alternatives-do-not-count rule, confirmed by direct side-by-side read of both files.
- web/src/api/local.ts is the original single-user FastAPI client moved unchanged; book/check-login/list-groups/serve in __main__.py are untouched below the new book-all/refresh/seal-keygen branches, so the single-user path is provably unaffected, not just claimed.
- Every apply-progress "Deviations from Design" entry (6 total, across Units 1-4) is a documented, justified, in-scope adjustment (require_upv_credentials flag, upsert_settings filling a design gap, etc.) rather than an unexplained divergence.
- Recurring size:exception requests (PR 1 about 505 lines, PR 2 about 927, PR 3 about 1629, PR 4 about 595, all over the 400-line default; PR 5 and PR 6 under budget) were already resolved by the ask-on-risk to stacked-to-main decision at slice granularity per tasks.md's forecast table, not re-litigated here, but flagged as WARNING since actual overruns reached up to 4x the forecast.

## Issues

### CRITICAL
None found.

### WARNING

1. Live-check-only scenarios (by design, cannot run locally): RLS cross-user isolation (booking-queue, user-accounts specs), account-deletion cascade, sign-in and manual throttle atomicity under concurrency (claim_refresh), GitHub Pages reachability, and daily keepalive actually preventing project pause. All are statically reviewed and consistent with spec and design, but none has runtime evidence yet. Recommend running design.md's "Manual checklist against supabase start" (or the live project) around OWNER 1.5, and exercising OWNER 6.2/6.3 to close this gap for real.
2. PR size overruns: 4 of 6 slices (PR 1-4) landed 1.3x to 4x over both the 400-line default and their own forecast, up to about 1629 changed lines for PR 3. Delivery strategy already resolved via stacked-to-main, and each overrun is individually justified in apply-progress.md, but reviewer load for PR 3 in particular is substantial.
3. app_settings' max_per_activity/max_sessions: the booking-queue spec's parenthetical mention of max_sessions (default 10, across all activities) is not enforced anywhere in the multi-user path, but this mirrors pre-existing single-user behavior (adapters/web/api.py also never checks max_sessions; the tool only ever manages one activity's queue), so this is a pre-existing scope limitation carried forward unchanged, not a regression introduced by this change.
4. keepalive.yml's "non-blocking" guarantee is structural rather than explicit: since keepalive.yml and book.yml are fully independent workflows with no trigger dependency between them, a keepalive failure cannot block the weekly batch today, but nothing in the workflow files makes that coupling explicitly impossible for a future change.

### SUGGESTION

1. Consider adding a Deno-side unit test for refresh/index.ts's branch logic (signin returns a silent 200 versus manual returns 429) now that the logic has grown past the Phase 1 skeleton; currently only reachable via live or manual testing per design.md's own Testing Strategy table, an accepted gap that would be cheap to close.
2. A future pass could cross-check README.md's new sections against the live .env.example and workflow secrets once OWNER 0.3 is complete, to catch any documentation drift after the first real deployment.

## Result Contract

- status: done
- executive_summary: PASS WITH WARNINGS. 0 CRITICAL, 4 WARNING, 2 SUGGESTION; both test commands pass (117 pytest, web build clean), every non-OWNER task is complete, and all SQL/Edge/live-workflow scenarios are statically sound but still need a live Supabase check before OWNER cutover.
- artifacts: openspec/changes/multi-user-web/verify-report.md
- next_recommended: sdd-archive (implementation is complete and sound; remaining OWNER tasks are manual infrastructure steps outside SDD scope, not blockers to archiving this change)
- risks: (1) no runtime evidence yet for RLS, cascade, throttle concurrency, Pages, and keepalive; recommend the owner run the supabase start checklist and OWNER 6.2/6.3 before fully relying on multi-user book-all; (2) PR 1-4 significantly exceeded the review budget, already accepted under stacked-to-main
- skill_resolution: paths-injected

## Key Learnings

1. Six stacked PR slices each carried their own apply-progress unit with evidence, deviations, and rollback boundary, making cross-slice verification tractable despite about 5400 changed lines total.
2. The sealed-credential interop between browser libsodium-wrappers and runner PyNaCl was proven with a fixture actually generated by the real JS library, not just round-tripped through PyNaCl alone, a stronger interop test than either side testing itself.
3. Turn-taking correctness (no starvation, exclusive UPV access) was verified with both a logical fairness test and a real-thread mutual-exclusion test in test_turns.py, not just a single-threaded simulation.
4. SQL, RLS, Edge Function, and live-workflow scenarios were consistently and correctly flagged as needs-live-check in apply-progress rather than falsely claimed as tested, which made this verification pass straightforward to scope.
5. The single-user book path's independence from the new multi-user code was confirmed structurally through unchanged code paths in __main__.py and api/local.ts moved verbatim, rather than merely asserted.
