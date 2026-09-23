# Platform Operations Specification

## Purpose

Keep the multi-user platform running at zero monthly cost: the frontend served from GitHub Pages, the free Supabase project kept awake, and public repository logs free of any per-user identifying information.

## Requirements

### Requirement: GitHub Pages Hosting
The system MUST serve the React/Vite frontend from GitHub Pages at a project path, with the Vite build configured with the correct `base` so all assets resolve under that path.

#### Scenario: Deployed app is reachable
- GIVEN a successful frontend build and Pages deployment
- WHEN a visitor navigates to the published Pages URL
- THEN the app loads and all static assets (JS, CSS) resolve correctly under the Pages project path

### Requirement: Daily Keepalive
The system MUST run a daily scheduled job that pings the Supabase free project so it is not auto-paused due to inactivity.

#### Scenario: Keepalive prevents pause
- GIVEN the Supabase free project would auto-pause after a period of inactivity
- WHEN the daily keepalive job runs
- THEN it performs a request against the project
- AND the project's inactivity timer is reset, preventing auto-pause

#### Scenario: Keepalive failure is visible but non-blocking
- GIVEN the keepalive job fails to reach the project
- WHEN the failure occurs
- THEN it is recorded in the workflow run status
- AND it does not block or fail the weekly batch booking workflow

### Requirement: Public Log Hygiene
Workflow logs in the public repository MUST NOT contain user-identifying information: no UPV usernames, no group codes, and no per-user booking details. Multi-user batch logs MUST reference users only by an opaque index or identifier that cannot be traced back to a real identity from the log alone.

#### Scenario: Batch log uses opaque references only
- GIVEN a completed multi-user weekly batch run
- WHEN the public workflow log is inspected
- THEN each processed user is referenced only by an opaque index (e.g. "user 2 of 5")
- AND no UPV username, group code, email address, or personal detail appears in the log

#### Scenario: Error messages are scrubbed
- GIVEN a user's booking attempt fails with an error that could contain identifying details
- WHEN that error is logged
- THEN the logged message excludes UPV usernames, emails, and group codes before being written to the public log
