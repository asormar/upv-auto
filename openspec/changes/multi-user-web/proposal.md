# Proposal: Multi-User Web

## Intent

upv-auto serves one user through env credentials and `config.yaml`. Other UPV students should use it from a URL at zero cost (free tiers, no credit card), keeping GitHub Actions as the only component that logs into UPV.

## Scope

### In Scope
- Supabase: email auth, Postgres + RLS (queues, cached schedule, results), Realtime, dispatch Edge Function, daily keepalive.
- Browser-sealed UPV credentials (`crypto_box_seal`); private key only as an Actions secret.
- Saturday batch (cron-job.org, 09:45 Europe/Madrid, unchanged): turn-taking per-user run (no two users hit UPV at once), failure isolation, per-user result records.
- Schedule refresh on sign-in (throttled) and manual button (rate-limited); loading-state hook only.
- Per-user limits (10/6) and queue semantics; global activity.
- Per-user email via `EmailNotifier`, one shared sender.
- Account deletion cascades user data.
- GitHub Pages deploy; migrate the current user.

### Out of Scope
- Loading animation design (later, animation skills).
- Periodic refresh; matrix jobs; per-user activity.
- Backend server (FastAPI stays local-dev / `serve --demo`).

## Capabilities

### New Capabilities
- `user-accounts`: sign-up/in, session, deletion cascade.
- `credential-custody`: browser sealing, runner-only unsealing, no plaintext at rest or in logs.
- `booking-queue`: per-user queue with limits, alternatives, empty queue valid.
- `weekly-batch-booking`: turn-taking multi-user run, isolation, results, email.
- `schedule-refresh`: sign-in/manual triggers, throttle, rate limit, Realtime loading state.
- `platform-operations`: Pages hosting, keepalive, public-log hygiene.

### Modified Capabilities
None (no existing specs in `openspec/specs/`).

## Approach

Exploration approach 1. Domain and use cases stay untouched; a new Supabase adapter (PyNaCl unseal, queue read, result write) feeds the existing engine, and `book.yml` loops users. The Edge Function checks `auth.uid()`, rate-limits, and dispatches workflows. Six ~400-line slices: schema/keepalive/Edge skeleton; browser auth + sealing; Python adapter + batch loop; refresh flow; Pages + Vite `base`; migration + docs.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/upv_auto/adapters/` | New | Supabase adapter, unsealing |
| `src/upv_auto/__main__.py`, `config.py` | Modified | Multi-user driver; config stays local-dev |
| `.github/workflows/` | Modified/New | `book.yml` loop, refresh, keepalive, Pages |
| `web/src/` | Modified | Auth, sealing, Supabase client |
| `web/vite.config.ts` | Modified | Pages `base` |
| `supabase/` | New | Migrations, RLS, Edge Function |

**CI secrets: touched** (sealing private key, Supabase service key, dispatch token). **Booking window timing: unchanged**, but batch runtime grows per user.

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Batch exceeds timeout / misses window | Med | Validate runtime per N users; ordered queues |
| Identifiers leak in public logs | Med | Log audit; opaque indices only |
| One user aborts batch | Med | Per-user try/record |
| Gmail sending limits | Low | Monitor count |
| Custody of third-party credentials | Med | Sealed box, key rotation, deletion |

## Rollback Plan

Keep the single-user path (`config.yaml` + env secrets) working until migration. Revert `book.yml` to the single-user command; disable the Pages workflow; pause Supabase. Credentials are useless without the Actions private key; rotating it invalidates all sealed data.

## Dependencies

- Supabase free, cron-job.org, GitHub Pages; `libsodium-wrappers`, `PyNaCl`.

## Success Criteria

- [ ] A second student signs up, stores credentials, edits a queue, and receives a Saturday result email.
- [ ] One user's failure leaves others' bookings intact.
- [ ] Refresh completes in ~1-2 min with visible loading state.
- [ ] Public logs contain no user identifiers.
- [ ] Monthly cost remains zero.
