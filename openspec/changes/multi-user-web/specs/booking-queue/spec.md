# Booking Queue Specification

## Purpose

Let each signed-in user maintain their own ordered booking queue (primary slots and alternatives) within fixed limits, stored per-user in Supabase and isolated by RLS.

## Requirements

### Requirement: Per-User Queue Limits
The system MUST apply the existing `LimitsConfig` rules per user, unchanged from the single-user tool: a queue holds at most `max_per_activity` (default 6) bookings, because UPV lets one person hold at most 6 sessions of this activity (and at most `max_sessions`, default 10, across all activities). Each booking may list alternative groups; alternatives do not count towards the limit because at most one group per booking is taken.

#### Scenario: Booking accepted under limit
- GIVEN a user with 5 bookings in their queue
- WHEN they add one more booking
- THEN the booking is accepted
- AND the queue now has 6 bookings

#### Scenario: Booking rejected over limit
- GIVEN a user with 6 bookings already queued
- WHEN they attempt to add another booking
- THEN the system rejects the addition with a message explaining the UPV limit
- AND the queue remains at 6 bookings

#### Scenario: Alternatives do not count
- GIVEN a user with 6 bookings, one of which lists 2 alternative groups
- WHEN the limit is evaluated
- THEN the queue counts as 6 bookings, not 8

### Requirement: Empty Queue Is Valid
The system MUST treat an empty booking queue as a valid state requiring no booking attempt for that user.

#### Scenario: Batch skips empty queue
- GIVEN a user with zero queue entries
- WHEN the weekly batch processes all users
- THEN no booking attempt is made for that user
- AND no error or failure record is produced for that user

### Requirement: Queue Isolation by RLS
The system MUST enforce, via Postgres RLS, that a user can read, add, reorder, or remove only entries in their own queue.

#### Scenario: Cross-user queue access denied
- GIVEN two signed-in users A and B
- WHEN user A attempts to read or modify user B's queue via the API
- THEN the request is denied
- AND user B's queue is unchanged

### Requirement: Queue Editing
A signed-in user MUST be able to add, remove, and reorder entries in their own queue before the weekly batch runs.

#### Scenario: User reorders queue
- GIVEN a user with multiple queued entries
- WHEN they change the entry order
- THEN the stored queue reflects the new order
- AND the weekly batch honors that order when attempting bookings
