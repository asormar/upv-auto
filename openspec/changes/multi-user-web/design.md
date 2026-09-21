# Design: Multi-User Web

## Technical Approach

Supabase holds identity, sealed credentials, queues, cached schedules, refresh requests and results under RLS. GitHub Actions stays the only UPV client: `book.yml` gains a `book-all` mode, and a new `refresh.yml` serves one opaque request. Python changes are additive: new application services and ports, plus httpx/PyNaCl adapters. `domain/`, the existing use cases and the single-user `config.yaml` path stay unchanged. The front keeps its component contracts behind `api.ts`, which selects the Supabase backend or the local FastAPI backend.

## Architecture Decisions

| Topic | Choice | Rejected | Rationale |
|---|---|---|---|
| Batch execution | One thread per user, gated by a fair `TurnScheduler`: exactly one user is active; `TurnTakingClock.sleep()` yields the turn | Run each user to completion; free-running threads; matrix | The window is 10:01–10:04, so running users to completion would starve user 2+ while user 1 retries. With turn-taking, UPV interactions still never overlap (the spec's "one at a time"), CAS logins stay serialized, and `BookSlotUseCase` is reused untouched |
| Login timing | Each use case logs in during its first turn, then sleeps until the window opens | Explicit pre-login decorator | Logins already happen sequentially before 10:01, so no extra code is needed |
| Per-user config | `dataclasses.replace(load_config(), credentials=…, bookings=…, email=None)` | New config loader | Global settings stay in `config.yaml` |
| Notification | `BufferedNotifier` per user; one email per user, sent sequentially after all threads join | SMTP inside a turn | Keeps SMTP out of the window, sends one mail per user, and never mixes users |
| Python Supabase client | httpx PostgREST adapter using the service-role key | supabase-py | httpx is already pinned, while supabase-py pulls in a heavy dependency tree |
| Sealed format | base64 `crypto_box_seal(JSON{v,username,password})` plus a `key_id` | Encrypting inside the Edge Function | Only the runner holds the private key |
| Key rotation | `SEAL_PRIVATE_KEYS` secret = JSON `{key_id: base64 sk}`; the front ships `VITE_SEAL_PUBLIC_KEY` and `VITE_SEAL_KEY_ID`; a stale `key_id` prompts re-entry; the old key is removed after one Saturday | Single fixed key | Rotation must invalidate old data, and the grace period avoids a missed Saturday |
| Refresh dispatch | Edge Function `refresh` → SQL `claim_refresh(trigger)` → `workflow_dispatch` with input `request_id` only | Passing the user id or email | Public run inputs show only a random UUID |
| Rate limiting | Inside `claim_refresh` (security definer, `pg_advisory_xact_lock` per user), based on `refresh_requests`: sign-in throttle 6 h since the last `done`; manual 1 per 5 min and 10 per day; a pending request is reused; pending requests older than 15 min expire | Edge-memory counters | Edge Functions are stateless, and the check-and-insert is atomic in SQL |
| Refresh concurrency | No `concurrency:` group on `refresh.yml` | A shared group | GitHub keeps only one pending run per group and cancels the others |
| Keepalive | `keepalive.yml` (`workflow_dispatch` from a daily cron-job.org job, plus `schedule` as backup) calls `rpc/keepalive` | Schedule only | GitHub disables schedules after 60 days without commits |
| Schedule cache | Raw groups without `booking_path`; `build_days` is ported to TypeScript | Storing rendered days | Queue flags depend on the queue, which is edited in the client |
| Front backend | `VITE_BACKEND=local` keeps the FastAPI fetch path; Supabase is the default | Dropping FastAPI | `serve --demo` and local dev keep working |
| Account deletion | Edge Function `delete-account` → `auth.admin.deleteUser`; every FK uses `on delete cascade` | Client-side deletes | Requires the service role, and gives one cascade point |
| Sign-up | Email confirmation disabled | Confirmation through the built-in SMTP | The spec requires an immediate session, and the free built-in SMTP is heavily rate-limited |

## Schema (`supabase/migrations/0001_multi_user.sql`)

Every table has RLS enabled. Every per-user table has `user_id uuid references auth.users on delete cascade`, and each user policy is `using/with check (user_id = auth.uid())`. The one exception is `app_settings`: a single global row (`id = 1`) with no `user_id`, readable by signed-in users and writable only by the service role.

| Table | User (anon key + JWT) | Service role |
|---|---|---|
| `upv_credentials(user_id pk, sealed, key_id, updated_at)` | select/insert/update/delete own | read |
| `booking_queue(user_id pk, bookings jsonb, updated_at)` | select/insert/update own | read |
| `schedules(user_id pk, groups jsonb, fetched_at)` | select own | write |
| `refresh_requests(id uuid pk, user_id, trigger, status, error_code, created_at, finished_at)` | select own (Realtime publication) | update |
| `batch_results(id, user_id, run_id, status, summary, created_at)` | select own | insert |
| `app_settings(id=1, settings jsonb)` | select | upserted from `config.yaml` on every run |

The `validate_queue` trigger allows at most `max_per_activity` (6) bookings; alternatives do not count. It also enforces codes matching `^[A-Z]{3}\d{3}$` and unique preferred codes. `batch_roster()` returns non-empty queues joined with credentials and `auth.users.email`, and is executable only by `service_role`.

## Data Flow

    Browser --seal(pk)--> upv_credentials     Browser --RLS--> booking_queue
    Browser --JWT--> Edge refresh --claim_refresh--> refresh_requests
                          └--> dispatch refresh.yml(request_id)
    refresh.yml: request -> unseal -> fetch_schedule -> schedules; status done|failed
    Realtime(refresh_requests) --> useRefreshStatus --> reload schedule
    cron-job.org 09:45 -> book.yml(book-all) -> batch_roster
        -> turn-taking BookSlotUseCase per user -> batch_results -> one email per user

## Log Hygiene (multi-user commands)

1. A `RedactingFilter` on the root handler replaces registered secrets (username, password, email) with `***`, `[A-Z]{3}\d{3}` with `[group]`, email addresses with `[email]`, and UUIDs with `[id]`.
2. On Actions, emit `::add-mask::` for every unsealed value before it is used.
3. Logs name users only as `user i/N`. Per-user exceptions log only `type(exc).__name__`.
4. The `httpx` logger runs at WARNING, because at INFO it logs URLs that contain user ids.
5. `book-all` and `refresh` upload no artifacts, because CAS screenshots show usernames. Both use a fixed `run-name`.

## Timing Budget

Setup takes about 3 minutes, so logins start around 09:49 at 20–40 s each and must finish before 10:01. That covers about 15 users; later users still book, just later. During the window each turn makes 1–2 requests. `timeout-minutes: 30` is kept, and the run ends around 10:06.

## File Changes

| File | Action | Description |
|---|---|---|
| `supabase/migrations/0001_multi_user.sql` | Create | Tables, RLS, trigger, `claim_refresh`, `batch_roster`, `keepalive`, Realtime publication |
| `supabase/functions/refresh/index.ts`, `delete-account/index.ts` | Create | `getUser()`, then claim + dispatch or delete; CORS limited to the Pages origin |
| `src/upv_auto/ports.py` | Modify | Add `UserDirectory`, `CredentialOpener` |
| `src/upv_auto/app/turns.py` | Create | `TurnScheduler`, `TurnTakingClock`, `BufferedNotifier` |
| `src/upv_auto/app/run_batch.py`, `refresh_user.py` | Create | Multi-user services |
| `src/upv_auto/adapters/supabase_rest.py` | Create | PostgREST repository |
| `src/upv_auto/adapters/sealed_box.py` | Create | PyNaCl opener and keygen |
| `src/upv_auto/adapters/log_redaction.py` | Create | Log filter and masks |
| `src/upv_auto/__main__.py` | Modify | Subcommands `book-all [--now]`, `refresh --request-id`, `seal-keygen` |
| `pyproject.toml` | Modify | Extra `multiuser = ["pynacl>=1.5"]` |
| `.github/workflows/book.yml` | Modify | `book-all` mode, Supabase and seal secrets, no artifacts for `book-all` |
| `.github/workflows/refresh.yml`, `keepalive.yml`, `pages.yml` | Create | Refresh (validated UUID input via env, timeout 10), keepalive, Pages deploy |
| `web/vite.config.ts` | Modify | `base: process.env.VITE_BASE_PATH ?? "/"` |
| `web/package.json` | Modify | `@supabase/supabase-js`, `libsodium-wrappers` |
| `web/src/api.ts` | Modify | Facade: same exports plus `requestRefresh`, `saveCredentials`, `deleteAccount` |
| `web/src/api/local.ts`, `api/supabase.ts`, `scheduleView.ts`, `seal.ts` (lazy import), `useRefreshStatus.ts` | Create | Backends, `build_days` port, sealing, Realtime hook |
| `web/src/components/AuthGate.tsx`, `SignIn.tsx`, `CredentialsForm.tsx` | Create | Auth and credentials gate |
| `web/src/App.tsx`, `main.tsx` | Modify | Drive `refreshing` from the hook; wrap the app in `AuthGate` |
| `README.md` | Modify | Setup, rotation, migration, local dev |

## Interfaces / Contracts

```python
class UserDirectory(Protocol):
    def roster(self) -> list[UserRecord]: ...  # non-empty queues only
    def record_result(self, user_id: str, run_id: str, status: str, summary: str) -> None: ...
    def claim_request(self, request_id: str) -> RefreshJob | None: ...
    def save_schedule(self, user_id: str, groups: dict[str, GroupAvailability]) -> None: ...
    def finish_request(self, request_id: str, ok: bool, error_code: str | None) -> None: ...

class CredentialOpener(Protocol):
    def open(self, sealed: str, key_id: str) -> Credentials: ...  # raises CredentialsUnavailable
```

Result status values are `booked` (exit 0), `incomplete` (exit 1), `credentials_unavailable` and `error`.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | Turn fairness and single active user, `BufferedNotifier`, `RedactingFilter`, sealed-box round trip, wrong or unknown key | pytest |
| Integration | `run_batch`: user B's login fails while A and C book; empty queue produces no row and no mail; an exception stays isolated; `caplog` contains no codes or usernames | pytest + `tests/fakes.py` |
| Integration | `supabase_rest` requests; `refresh_user` state transitions; rejection of a non-UUID `--request-id` | `httpx.MockTransport`, pytest |
| Interop | A committed fixture sealed by libsodium-wrappers, opened with PyNaCl | pytest |
| Front | Types and build | `npm run build --prefix web` |
| SQL/Edge | Cross-user RLS, queue limit 6, throttle | Manual checklist against `supabase start` |

## Threat Matrix

| Boundary | Applicability |
|---|---|
| Documentation-like paths | N/A: no file classification or execution |
| Git repository selection | N/A: no git commands; dispatch is a GitHub REST call to a fixed repo and workflow |
| Commit state | N/A: nothing commits |
| Push state | N/A: nothing pushes |
| PR commands | N/A: no PR automation |

The adjacent risk is workflow-input injection. `request_id` reaches the script only through `env` and is checked as a UUID before use (RED test: the CLI rejects a non-UUID value).

## Migration / Rollout

Delivery follows the proposal's six slices. Migration steps: the owner signs up on Pages and enters credentials and the queue; runs `book-all --now` with only this account; switches the cron-job.org body to `mode: book-all`; after one successful Saturday, deletes the `UPV_USERNAME`/`UPV_PASSWORD` secrets. Rollback: switch the cron body back to `book`.

## Open Questions

- [x] Resolved: the spec's "one at a time" means no overlapping UPV interaction (turn-taking); the spec was updated to say so.
- [ ] The throttle values (6 h, 5 min, 10/day) are design defaults; the specs leave them open.
