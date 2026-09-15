# upv-auto

Automates booking a UPV (Universitat Politècnica de València) sports facility
slot. Booking windows open every Saturday at 10:00 Europe/Madrid, and the
site sometimes lags — so this retries from 10:00:00 to 10:03:00.

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

**The booking endpoints are not mapped yet.** `HttpxBookingClient.book()` is
a deliberate stub that raises `NotImplementedError` with instructions. Wire
it up once you've inspected the real booking request/response shapes (see
comments in that file). Everything else — login, session verification,
retry loop, notifications, CLI, GitHub Actions workflow, tests — is real and
working.

## Local setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e ".[dev]"
python -m playwright install chromium   # only needed to actually run a login
cp .env.example .env          # fill in UPV_USERNAME / UPV_PASSWORD
```

Edit `config.yaml`: the `slots` list has placeholder `facility`/`sport`
values (`"TODO"`) — replace them once known. The first slot is the
preferred one; alternatives are tried in order if it's taken.

Run the tests (no network, no real browser):

```bash
pytest -q
```

Commands:

```bash
python -m upv_auto check-login          # log in, verify the session, exit
python -m upv_auto book                 # wait for the window, attempt to book
python -m upv_auto book --now           # skip waiting (local testing only)
```

## GitHub Actions setup

1. Create a **private** GitHub repository and push this code.
2. Add repository secrets (Settings → Secrets and variables → Actions):
   - `UPV_USERNAME`, `UPV_PASSWORD` — required.
   - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — optional; without them,
     notifications just go to the workflow log (console fallback).
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
