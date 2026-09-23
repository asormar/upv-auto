# User Accounts Specification

## Purpose

Let any UPV student create an account, sign in, and remove their account and all associated data, using Supabase email authentication as the identity boundary for the multi-user web app.

## Requirements

### Requirement: Email Sign-Up
The system MUST let a visitor create an account with an email address and password via Supabase Auth.

#### Scenario: Successful sign-up
- GIVEN a visitor with a valid, unused email address
- WHEN they submit sign-up with a valid password
- THEN the system creates an authenticated user record
- AND the user is signed in with an active session

#### Scenario: Duplicate email rejected
- GIVEN an email address already registered
- WHEN a visitor attempts sign-up with that email
- THEN the system rejects the sign-up
- AND no duplicate account is created

### Requirement: Email Sign-In
The system MUST let a registered user sign in with their email and password and establish a session.

#### Scenario: Successful sign-in
- GIVEN a registered user with correct credentials
- WHEN they submit sign-in
- THEN the system establishes an authenticated session
- AND the user can access only their own data

#### Scenario: Invalid credentials rejected
- GIVEN a registered user submitting an incorrect password
- WHEN they attempt sign-in
- THEN the system rejects the attempt
- AND no session is established

### Requirement: Row-Level Access Isolation
The system MUST enforce, via Postgres RLS, that an authenticated user can read and write only rows owned by their own `auth.uid()`.

#### Scenario: User cannot read another user's data
- GIVEN two signed-in users A and B
- WHEN user A queries queue, schedule cache, or result data
- THEN only rows owned by user A are returned
- AND user B's rows are never visible to user A

### Requirement: Account Deletion Cascade
The system MUST let a signed-in user delete their account, and this deletion MUST cascade to remove all data owned by that user: sealed credentials, booking queue entries, cached schedule state, and result records.

#### Scenario: Deletion removes all owned data
- GIVEN a signed-in user with sealed credentials, a queue, and past results
- WHEN the user confirms account deletion
- THEN the auth account is removed
- AND all rows owned by that user's `auth.uid()` across every table are removed
- AND no residual sealed credential or queue data remains for that user

#### Scenario: Deletion does not affect other users
- GIVEN two users, each with their own data
- WHEN one user deletes their account
- THEN the other user's account and data remain fully intact
