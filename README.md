# upv-auto

Automates booking a UPV (Universitat Politècnica de València) sports facility
slot. Booking opens every Saturday at 10:00 Europe/Madrid, but UPV sometimes
keeps serving the previous week's table for a while and the page has no week
indicator — so this starts at 10:01:00 and retries until 10:04:00.

Runs for free on GitHub Actions (private repo). It is triggered remotely by
[cron-job.org](https://cron-job.org) at 09:45 Europe/Madrid, which dispatches
the workflow with a few minutes of margin before the window opens.

## How it works

Hybrid approach, hexagonal architecture:

- **Playwright** performs the CAS login (`adapters/playwright_auth.py`) and
  exports the resulting cookies + user agent as a `Session`.
- **httpx** replays that session over plain HTTP to verify it
  (`adapters/httpx_session.py`) and to perform the actual booking requests
  (`adapters/httpx_booking.py`) — much faster than driving a browser during
  the retry window.
- `app/book_slot.py` and `app/check_login.py` hold the use cases; `ports.py`
  defines the interfaces adapters implement; `domain/` has no I/O.

**Booking works by scraping and replaying links, not calling a JSON API**,
and downloads the activity table **at most once per round**, no matter how
many bookings are pending. `HttpxActivityTableClient`
(`adapters/httpx_booking.py`) exposes two calls:

- `fetch_groups()` GETs the weekly activity table for the configured
  activity (`sic_depact.HSemActividades?...`) and parses it
  (`adapters/upv_activities_parser.py`, stdlib `html.parser` only) into a
  `{group_code: GroupAvailability}` map — one entry per group cell, with its
  state (`BOOKABLE` / `FULL` / `ENROLLED` / `UNAVAILABLE`), free-place count,
  and (for bookable groups) the exact booking link scraped from that cell.
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

## Local setup

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

bookings:
  - group_code: MUS021            # Tuesday 12:30-13:30
  - group_code: MUS022            # Tuesday 13:30-14:30
    alternatives: [MUS037]        # Wednesday 13:30-14:30 if MUS022 is full
```

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
python -m upv_auto list-groups          # log in, print each group's state (pick group_code values)
python -m upv_auto book                 # wait for the window, attempt to book
python -m upv_auto book --now           # skip waiting (local testing only)
```

## GitHub Actions setup

1. Create a **private** GitHub repository and push this code.
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
  help debugging. Passwords and cookie values are never logged.
