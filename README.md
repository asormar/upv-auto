# upv-auto

Automates booking a UPV (Universitat Politècnica de València) sports facility
slot. Booking opens every Saturday at 10:00 Europe/Madrid, but UPV sometimes
keeps serving the previous week's table for a while and the page has no week
indicator — so this starts at 10:01:00 and retries until 10:04:00.

Two ways to run it:

- **Multi-user web app** (recommended): sign up on the deployed GitHub Pages
  site, enter your UPV credentials once, pick your hours, and a shared GitHub
  Actions run books for every signed-up user on Saturday. See
  [Multi-user architecture](#multi-user-architecture) below.
- **Single-user, `config.yaml`-only**: the original mode — edit `config.yaml`
  by hand or run the local web UI, no Supabase project needed. See
  [Local setup](#local-setup).

Both run for free on GitHub Actions (standard runners are unmetered on public
repositories) and are triggered remotely by
[cron-job.org](https://cron-job.org) at 09:45 Europe/Madrid, a few minutes of
margin before the window opens.

## How it works

Hybrid approach, hexagonal architecture:

- **Playwright** performs the CAS login (`adapters/playwright_auth.py`) and
  exports the resulting cookies + user agent as a `Session`.
- **httpx** replays that session over plain HTTP to verify it
  (`adapters/httpx_session.py`) and to perform the actual booking requests
  (`adapters/httpx_booking.py`) — much faster than driving a browser during
  the retry window.
- `app/` holds the use cases: `book_slot.py`, `check_login.py`,
  `list_groups.py`, and `fetch_schedule.py` — log in, download and parse the
  table — which `list-groups` and the web UI share. `ports.py` defines the
  interfaces adapters implement; `domain/` has no I/O.

**Booking works by scraping and replaying links, not calling a JSON API**,
and downloads the activity table **at most once per round**, no matter how
many bookings are pending. `HttpxActivityTableClient`
(`adapters/httpx_booking.py`) exposes two calls:

- `fetch_groups()` GETs the weekly activity table for the configured
  activity (`sic_depact.HSemActividades?...`) and parses it
  (`adapters/upv_activities_parser.py`, stdlib `html.parser` only) into a
  `{group_code: GroupAvailability}` map — one entry per group cell, with its
  state (`BOOKABLE` / `FULL` / `ENROLLED` / `UNAVAILABLE`), free-place count,
  the day and time read from the cell's position in the weekly grid, and (for
  bookable groups) the exact booking link scraped from that cell.
- `follow_booking()` GETs a bookable group's scraped link
  (`sic_depact.HSemActMatri?...`) — the booking id in that link
  (`p_codgrupo_mat`) is opaque and changes between groups, so it is always
  read from the table right before booking, never hardcoded. UPV redirects
  that request back to the now-updated activity table, so the response is
  parsed the same way and handed back as another table snapshot.

`app/book_slot.py` drives this each round: one `fetch_groups()` call, then
every pending booking is resolved against that same table in turn. A
`BOOKABLE` group gets `follow_booking()`'d, and **the table that call
returns replaces the round's table**, so the next pending booking is
resolved against the fresh data with no extra download. `FULL` moves to the
next alternative and re-evaluates it immediately, still within the same
table. Already `ENROLLED` is **not** automatically a success: the page has
no week indicator, so it may be the previous week's table — it only counts
as booked once this run has itself followed a booking link for that exact
group code (tracked per target as `attempted_codes`); otherwise it is
retried and, if it never changes, reported as "check manually".
`UNAVAILABLE` or missing means the window hasn't opened for that slot yet.

Any response whose final URL lands on `cas.upv.es` means the session has
expired; the run re-logs in at most once before giving up.

## Multi-user architecture

The deployed app is a static frontend on GitHub Pages talking directly to
Supabase, with GitHub Actions as the only thing that ever logs into UPV.

```
Browser (GitHub Pages)
  │  sign up / sign in (Supabase Auth)
  │  seal UPV credentials with a public key, write the booking queue
  ▼
Supabase (Postgres + RLS + Realtime + Edge Functions)
  │  upv_credentials · booking_queue · schedules · refresh_requests · batch_results
  │  refresh Edge Function: claim_refresh() → workflow_dispatch(refresh.yml)
  ▼
GitHub Actions (the only UPV client)
  book.yml (mode: book-all) ── cron-job.org, Saturday 09:45 Europe/Madrid
  refresh.yml               ── dispatched only by the refresh Edge Function
  keepalive.yml              ── cron-job.org, daily (+ a 60-day backup schedule)
  pages.yml                  ── builds and deploys web/ on every push to main
```

- **Browser**: React app (`web/`). Users never see UPV credentials again
  after entering them once — `web/src/seal.ts` encrypts them client-side with
  `crypto_box_seal` before they ever reach Supabase, using the public key
  baked into the build (`VITE_SEAL_PUBLIC_KEY`). Only the GitHub Actions
  runner holds the matching private key.
- **Supabase**: identity (Supabase Auth), sealed credentials, each user's
  booking queue, a cached schedule per user, and refresh/result tracking —
  all under Row-Level Security, so one user's Postgres row is invisible to
  another. `supabase/migrations/0001_multi_user.sql` is the full schema;
  `supabase/functions/` holds the two Edge Functions (`refresh`,
  `delete-account`).
- **GitHub Actions** stays the only thing that ever talks to UPV, exactly as
  in single-user mode — `book-all` just loops over every user with a
  non-empty queue instead of reading one `config.yaml`.

### What users see

1. Sign up on the deployed Pages URL (email + password, no confirmation
   email step).
2. Enter UPV username/password once — sealed in the browser, never sent or
   stored in plain text.
3. Pick hours from the live UPV table, same queue/alternatives UI as the
   single-user web UI.
4. The schedule refreshes automatically on sign-in (if the cached one is
   stale) and on demand via the "Actualizar" button, both rate-limited
   server-side; a loading state shows while a refresh is in flight.
5. Every Saturday at 09:45 Europe/Madrid, `book-all` books every signed-up
   user's queue in turn (one user's UPV session active at a time, so nobody
   blocks anybody else) and sends each user their own summary email.

## Owner setup (one-time)

Everything below is done once by whoever runs the deployment — not by each
user. Checklist order matters (secrets before the workflow that reads them).

- [ ] **Supabase project**: create a free-tier project, then apply
      `supabase/migrations/0001_multi_user.sql` (SQL editor or
      `supabase db push`) and deploy both Edge Functions:
      `supabase functions deploy refresh` and
      `supabase functions deploy delete-account`.
- [ ] **Edge Function secrets** (`supabase secrets set NAME=value`, not
      GitHub Actions secrets — these live in the Supabase project):

  | Secret | Value |
  |--------|-------|
  | `ALLOWED_ORIGIN` | The deployed Pages origin, e.g. `https://<owner>.github.io` (CORS allow-list) |
  | `GITHUB_REPO` | `owner/repo` — where `refresh.yml` gets dispatched |
  | `GITHUB_DISPATCH_TOKEN` | A fine-grained PAT scoped to this one repo, **Actions: Read and write** only |

  `SUPABASE_URL`, `SUPABASE_ANON_KEY`, and `SUPABASE_SERVICE_ROLE_KEY` do
  **not** need to be set by hand — Supabase injects them into every deployed
  Edge Function automatically.
- [ ] **`seal-keygen`**: run `python -m upv_auto seal-keygen` (needs the
      `multiuser` extra: `pip install -e ".[multiuser]"`). It prints a fresh
      key pair — copy each value where it says:
  - `VITE_SEAL_PUBLIC_KEY` and `VITE_SEAL_KEY_ID` → GitHub Actions secrets
    (read by `pages.yml`, baked into the built frontend).
  - The printed `SEAL_PRIVATE_KEYS` entry → merge into the
    `SEAL_PRIVATE_KEYS` GitHub Actions secret, a JSON object of
    `{key_id: private_key}` (start with just the one entry the first time).
- [ ] **GitHub Actions secrets** (Settings → Secrets and variables →
      Actions → Secrets), read by `book.yml`, `refresh.yml`, `keepalive.yml`,
      and `pages.yml`:

  | Secret | Used by |
  |--------|---------|
  | `SUPABASE_URL` | `book.yml`, `refresh.yml`, `keepalive.yml` |
  | `SUPABASE_SERVICE_ROLE_KEY` | `book.yml`, `refresh.yml`, `keepalive.yml` |
  | `SEAL_PRIVATE_KEYS` | `book.yml`, `refresh.yml` |
  | `VITE_SUPABASE_URL` | `pages.yml` |
  | `VITE_SUPABASE_ANON_KEY` | `pages.yml` |
  | `VITE_SEAL_PUBLIC_KEY` | `pages.yml` |
  | `VITE_SEAL_KEY_ID` | `pages.yml` |

  Plus the dispatch PAT (see [cron-job.org setup](#cron-job-org-setup)
  below) — the same fine-grained PAT works for `book-all` and the daily
  keepalive dispatch; it does not need to be a repository secret, only
  cron-job.org's own stored credential.
- [ ] **Enable GitHub Pages**: repo Settings → Pages → Source →
      "GitHub Actions". `pages.yml` builds and deploys `web/` on every push
      to `main` that touches `web/**`, or on manual dispatch.
- [ ] **cron-job.org jobs** — two, in addition to any single-user job already
      set up per [cron-job.org setup](#cron-job-org-setup):
  - Saturday 09:45 Europe/Madrid, same `book.yml` dispatch URL, body
    `{"ref": "main", "inputs": {"mode": "book-all"}}`.
  - Daily, any time, dispatching `keepalive.yml` instead:
    `POST https://api.github.com/repos/<OWNER>/<REPO>/actions/workflows/keepalive.yml/dispatches`
    with the same headers and body `{"ref": "main"}`. This exists because a
    free Supabase project pauses after a week of no activity, and GitHub
    disables `schedule:` triggers after 60 days without a commit — the daily
    ping keeps the project (and, as a backup, the workflow's own `schedule:`
    trigger) alive.

## Key rotation

Rotate the sealing key pair if the private key may have leaked, or on a
regular schedule. Rotation invalidates every already-sealed credential —
each affected user must re-enter their UPV credentials once.

1. Run `python -m upv_auto seal-keygen --key-id v2` (bump the id each time).
2. Add its `VITE_SEAL_PUBLIC_KEY`/`VITE_SEAL_KEY_ID` as the new GitHub
   Actions secret values (this replaces the values `pages.yml` bakes into
   the next build) and merge its `SEAL_PRIVATE_KEYS` entry into the existing
   JSON secret — **keep the old `key_id` in `SEAL_PRIVATE_KEYS` for now**.
3. Redeploy Pages (push to `main`, or dispatch `pages.yml` manually) so new
   sign-ups and re-entries seal against `v2`.
4. A user whose stored credential still carries the old `key_id` is prompted
   to re-enter it (`CredentialOpener` raises `CredentialsUnavailable` for an
   unknown key). Give this at least one full Saturday.
5. Once every stored credential uses the new `key_id` (or after one
   Saturday's `book-all` run has flagged the stragglers), remove the old
   entry from `SEAL_PRIVATE_KEYS`.

## Migrating the current single user

For an existing single-user deployment moving to the multi-user app, without
losing a Saturday of booking:

1. Complete [Owner setup](#owner-setup-one-time) above — the Supabase
   project, Edge Functions, secrets, and Pages deploy — while the existing
   single-user `book` cron job keeps running unchanged.
2. Sign up on the deployed Pages URL as the same person, enter the same UPV
   credentials, and rebuild the same booking queue in the UI.
3. Validate end to end: run `python -m upv_auto book-all --now` locally or
   via a manual `book.yml` dispatch (`mode: book-all`), with only this one
   account signed up, and confirm the booking and the summary email arrive.
4. Switch the existing cron-job.org job's body from
   `{"inputs": {"mode": "book"}}` to `{"inputs": {"mode": "book-all"}}`
   (same dispatch URL, same PAT) and add the two new jobs from
   [Owner setup](#owner-setup-one-time) (`book-all`'s Saturday trigger is
   this same switched job — do not create a duplicate).
5. After one successful Saturday under `book-all`, delete the
   `UPV_USERNAME`/`UPV_PASSWORD` GitHub Actions secrets. `book-all` never
   reads them (`load_config(require_upv_credentials=False)`); they only
   remain useful for the single-user `book`/`check-login`/`list-groups`
   modes, which stay fully available (see [Local development](#local-setup)
   below) if you ever want to fall back.

Rollback at any point before step 5: switch the cron job's body back to
`{"inputs": {"mode": "book"}}`.

## Local setup

The commands below are the single-user, `config.yaml`-only path — no
Supabase project needed. They still work unchanged after the multi-user app
exists; `book-all`/`refresh` are additive commands, not replacements.

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"
python -m playwright install chromium   # only needed to actually run a login
cp .env.example .env          # fill in UPV_USERNAME / UPV_PASSWORD
```

Edit `config.yaml`: the `activity` section picks the UPV sports activity
(campus, `tipoact`, `codacti`); `bookings` lists every place to secure. Each
entry is booked independently; within an entry, `group_code` is preferred and
`alternatives` are tried in order if it is full, e.g.:

```yaml
activity:
  name: MUSCULACION
  campus: V
  tipoact: "6894"
  codacti: "21948"

# Optional; these are the defaults. UPV's Área de Deportes caps how many
# places one person may hold at the same time.
limits:
  max_sessions: 10
  max_per_activity: 6

bookings:
  - group_code: MUS021            # Tuesday 12:30-13:30
  - group_code: MUS022            # Tuesday 13:30-14:30
    alternatives: [MUS037]        # Wednesday 13:30-14:30 if MUS022 is full
```

An empty `bookings:` list is valid — a week you are not booking anything.
The run then exits 0 without logging in. Note that the web UI rewrites this
block when you change the queue, so hand-written comments on each booking do
not survive.

All bookings are attempted round-robin during the window, so one never waits
for another. You get a single summary email (`Booked 2/2: ...`), and the run
exits non-zero unless every booking succeeded.

For one-off tests, the workflow's `groups` input (or `book --group`, repeatable)
overrides `bookings`: space-separated bookings, commas for alternatives, e.g.
`MUS021 MUS022,MUS037`. Combine with `now` to start immediately.

Don't know the group codes yet? Run `python -m upv_auto list-groups` (see
below) to print every group for the configured activity along with its
current state and free places, then pick codes from there. Alternatives are
tried in order if the preferred group is full.

Run the tests (no network, no real browser):

```bash
pytest -q
```

Commands:

```bash
python -m upv_auto check-login          # log in, verify the session, exit
python -m upv_auto list-groups          # log in, print each group's state, day and time
python -m upv_auto book                 # wait for the window, attempt to book
python -m upv_auto book --now           # skip waiting (local testing only)
python -m upv_auto serve                # run the local web UI (see below)
```

## Web UI

A local web interface for picking what to book, instead of editing
`config.yaml` by hand. It is another driver over the same use cases: the API
(`adapters/web/api.py`) calls `fetch_schedule` for the real UPV table and
writes the chosen groups back into `config.yaml`; the booking itself still
runs on GitHub Actions on Saturday.

```bash
pip install -e ".[web]"
cd web && npm install && npm run build && cd ..
python -m upv_auto serve            # http://127.0.0.1:8000
```

`serve --demo` serves the sample table from `tests/fixtures/` instead of
logging into UPV — useful while working on the interface (it writes to
whatever `--config` points at, so point it at a copy).

For front-end development with hot reload, run the API and Vite side by side:

```bash
python -m upv_auto serve --demo --config config.demo.yaml
cd web && npm run dev               # proxies /api to port 8000
```

The UI shows one day at a time (the UPV week, day by day), your booking queue
in order, and the UPV limit as bubbles: at most 10 activity sessions at once,
of which at most 6 of this activity. Adding a group beyond the limit is
refused by the API, not just hidden in the UI.

`web/` is shared by both apps: set `VITE_BACKEND=local` (e.g. in
`web/.env.local`) to force the FastAPI backend above, even when
`VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY` are also set — this is what
keeps `serve --demo` and local frontend dev working without touching
Supabase. Unset (or any other value), it talks to Supabase directly; see
[Multi-user architecture](#multi-user-architecture).

## GitHub Actions setup (single-user mode)

Multi-user deployments should follow [Owner setup](#owner-setup-one-time)
instead — this section is for the original single-user `book` mode only,
kept working unchanged.

1. Push this code to a GitHub repository. Public is fine, and is what this
   one uses: credentials live in Actions secrets, never in the repository, and
   standard runners are unmetered for public repos. What a public repo does
   expose is `config.yaml` — which activity and which hours you book. Use a
   private repository if you would rather not publish that.
2. Add repository secrets (Settings → Secrets and variables → Actions):
   - `UPV_USERNAME`, `UPV_PASSWORD` — required.
   - `SMTP_USERNAME`, `SMTP_APP_PASSWORD` — optional email notifications via
     Gmail. `SMTP_USERNAME` is your Gmail address; `SMTP_APP_PASSWORD` is a
     Google app password (requires 2-Step Verification:
     https://myaccount.google.com/apppasswords), never your real password.
     Without them, notifications just go to the workflow log.
   - `NOTIFY_EMAIL_TO` — optional recipient; defaults to `SMTP_USERNAME`.
3. Test manually first: Actions → "Book UPV slot" → "Run workflow" →
   mode `check-login`. Do this on a weekday, well before relying on it.
4. Once `check-login` succeeds, the workflow is ready to be triggered by
   cron-job.org.

The workflow (`.github/workflows/book.yml`) only has a `workflow_dispatch`
trigger — no `schedule` — because cron-job.org drives the timing.

## cron-job.org setup

Single-user `book` mode, as set up above. For the multi-user `book-all` and
`keepalive` dispatch jobs, see [Owner setup](#owner-setup-one-time).

Create a job that sends, every Saturday at **09:45 Europe/Madrid**:

```
POST https://api.github.com/repos/<OWNER>/<REPO>/actions/workflows/book.yml/dispatches
```

Headers:

```
Authorization: Bearer <fine-grained PAT>
Accept: application/vnd.github+json
X-GitHub-Api-Version: 2022-11-28
Content-Type: application/json
```

Body:

```json
{"ref": "main", "inputs": {"mode": "book"}}
```

The PAT should be a **fine-grained personal access token** scoped to this
one repository only, with **Actions: Read and write** permission — nothing
else. Store it as the job's secret/header value in cron-job.org, not in this
repository.

## Notes

- Review UPV's sports facility booking rules before relying on this; you are
  responsible for complying with them.
- The bot never attempts to bypass a captcha or 2FA/OTP challenge — it stops
  and reports `AuthenticationBlocked` instead. If you hit this, log in
  manually and investigate why UPV is prompting for it.
- On any login failure, a screenshot is saved to `artifacts/` (gitignored
  locally, uploaded as a workflow artifact on failure, retained 3 days) to
  help debugging. Passwords and cookie values are never logged. `book-all`
  and `refresh` upload no artifacts at all — a CAS screenshot could expose
  one user's username. `book-all` also runs under a fixed `run-name`
  ("Multi-user booking batch", never per-user data); `refresh`'s only input
  is already an opaque UUID, so its run title is never identity-revealing.
- Multi-user logs never show a UPV username, password, group code, or email
  in the clear: a redacting filter masks them before they reach the GitHub
  Actions log, and `::add-mask::` is also emitted for each secret value.
  Users are logged only as `user i/N`.
