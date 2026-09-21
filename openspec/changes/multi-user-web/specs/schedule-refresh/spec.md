# Schedule Refresh Specification

## Purpose

Keep each user's cached UPV activity schedule reasonably fresh by refreshing on sign-in (throttled) and on manual request (rate-limited), while the frontend shows a visible loading state whenever a refresh is pending. Loading-animation design is out of scope; only the presence of a loading state is specified.

## Requirements

### Requirement: Sign-In Triggered Refresh
The system MUST trigger a schedule refresh when a user signs in, but MUST throttle this trigger so a refresh is not dispatched if the user's cached schedule was already refreshed within the throttle window.

#### Scenario: Sign-in refreshes stale cache
- GIVEN a user whose cached schedule was last refreshed longer ago than the throttle window
- WHEN they sign in
- THEN a refresh is dispatched for that user

#### Scenario: Sign-in within throttle window uses cache
- GIVEN a user whose cached schedule was refreshed less than the throttle window ago
- WHEN they sign in again
- THEN no new refresh is dispatched
- AND the existing cached schedule is served

### Requirement: Manual Refresh Rate Limiting
The system MUST let a signed-in user manually request a schedule refresh via a button, and MUST rate-limit repeated manual requests per user.

#### Scenario: Manual refresh accepted
- GIVEN a user who has not exceeded the manual refresh rate limit
- WHEN they trigger the manual refresh button
- THEN a refresh is dispatched for that user

#### Scenario: Manual refresh rejected when rate-limited
- GIVEN a user who has already reached the manual refresh rate limit within the current window
- WHEN they trigger the manual refresh button again
- THEN the request is rejected
- AND the cached schedule remains unchanged until the rate limit window resets

### Requirement: Visible Loading State During Pending Refresh
The frontend MUST show a visible loading state while a refresh for the current user is pending, and MUST clear it once the refreshed schedule (or an error) is received. The specific visual design of this loading state is out of scope for this capability.

#### Scenario: Loading state shown during refresh
- GIVEN a refresh has been dispatched for the current user and has not yet completed
- WHEN the user views the schedule
- THEN a visible loading indicator is displayed in place of, or alongside, the stale schedule

#### Scenario: Loading state clears on completion
- GIVEN a visible loading state during a pending refresh
- WHEN the refresh completes and updated schedule data (or an error) is received via Realtime
- THEN the loading state is cleared
- AND the current schedule (or an error indication) is displayed

### Requirement: Cached Schedule Served When Refresh Not Triggered
When no refresh is triggered or allowed, the system MUST serve the user's existing cached schedule rather than blocking on a fresh fetch.

#### Scenario: Cache served without refresh
- GIVEN a user with a valid cached schedule and no refresh currently pending
- WHEN they open the app
- THEN the cached schedule is displayed immediately without waiting for a refresh
