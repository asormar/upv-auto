# Weekly Batch Booking Specification

## Purpose

Run the Saturday UPV booking attempt for every eligible user in one GitHub Actions job, taking turns so that no two users talk to UPV at the same time, so that one user's failure never blocks another user's booking, and every user receives a recorded outcome and an email.

## Requirements

### Requirement: Turn-Taking Multi-User Run
The system MUST process all users with a non-empty booking queue in one GitHub Actions run, reusing the existing single-identity booking engine per user. Users take turns: at any moment at most one user interacts with UPV, and a user yields its turn whenever the engine waits (before the window or between retry rounds), so every user gets attempts inside the booking window instead of waiting for earlier users to finish.

#### Scenario: Batch processes all eligible users
- GIVEN three users each with a non-empty queue
- WHEN the Saturday batch runs
- THEN the system attempts bookings for each of the three users inside the booking window
- AND no two users interact with UPV at the same time
- AND each user's attempt uses only that user's unsealed credentials and queue

#### Scenario: A retrying user does not starve the others
- GIVEN user 1's first choice is still unavailable when the window opens
- WHEN user 1 waits before its next retry round
- THEN users 2 and 3 get their turns before user 1 retries

### Requirement: Per-User Failure Isolation
A failure while processing one user's booking (login failure, booking error, timeout) MUST NOT abort or skip processing for any other user in the batch.

#### Scenario: One user's failure does not block others
- GIVEN a batch with users A, B, and C, where user B's UPV login fails
- WHEN the batch runs
- THEN user A and user C are still processed
- AND user B's failure is recorded without stopping the run

### Requirement: Per-User Result Recording
The system MUST record a per-user result (success, failure, or reason) for every processed user after the batch completes.

#### Scenario: Result stored for each processed user
- GIVEN a completed batch run over multiple users
- WHEN the run finishes
- THEN a result record exists for every user who had a non-empty queue
- AND each record indicates the outcome for that specific user

### Requirement: Per-User Email Notification
The system MUST send each processed user an email describing their own booking outcome, using the existing `EmailNotifier` with a single shared sender.

#### Scenario: Email sent after processing
- GIVEN a user whose booking attempt completed (success or failure)
- WHEN the batch finishes processing that user
- THEN that user receives an email describing their own outcome
- AND the email contains no other user's information

### Requirement: Booking Window Timing Unchanged
The scheduled trigger MUST remain Saturday 09:45 Europe/Madrid via the existing cron-job.org dispatch, unchanged by the move to multiple users.

#### Scenario: Trigger time unchanged
- GIVEN the multi-user batch is deployed
- WHEN the scheduled trigger fires
- THEN it fires at Saturday 09:45 Europe/Madrid, identical to the prior single-user schedule
