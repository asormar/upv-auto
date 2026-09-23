# Credential Custody Specification

## Purpose

Store each user's UPV credentials safely so that no party except the GitHub Actions runner that performs the booking can ever read them in plaintext, while still allowing Supabase to persist and transport the sealed data.

## Requirements

### Requirement: Browser-Side Sealing
The system MUST seal UPV credentials (username and password) in the browser using `crypto_box_seal` against a public key before the credentials leave the client, and MUST NOT transmit or persist plaintext UPV credentials at any point.

#### Scenario: Credentials sealed before submission
- GIVEN a signed-in user entering their UPV username and password
- WHEN they submit the credential form
- THEN the browser seals the credentials with the public key before any network call
- AND only the sealed ciphertext is sent to Supabase

#### Scenario: Plaintext never stored
- GIVEN sealed credentials stored for a user
- WHEN the stored row is inspected in Postgres
- THEN only ciphertext is present
- AND no plaintext UPV username or password exists in any table

### Requirement: Runner-Only Unsealing
The system MUST restrict the sealed-box private key to the GitHub Actions runner environment as a repository/organization secret, and only the runner MAY unseal credentials, immediately before use for an UPV login.

#### Scenario: Runner unseals for booking
- GIVEN a batch job running on GitHub Actions with the private key available as a secret
- WHEN the runner processes a user's sealed credentials
- THEN it unseals them in-memory using PyNaCl
- AND the unsealed value is used only for that user's UPV login attempt

#### Scenario: No other component can unseal
- GIVEN the sealed private key is not present in the browser, Supabase, or the Edge Function environment
- WHEN any of those components handle sealed credential ciphertext
- THEN they cannot decrypt it
- AND no unsealing occurs outside the GitHub Actions runner

### Requirement: No Plaintext in Logs
Workflow and application logs MUST NOT contain plaintext UPV credentials at any log level.

#### Scenario: Batch log audit
- GIVEN a completed batch booking run with logs written to GitHub Actions
- WHEN the logs are inspected
- THEN no UPV username, password, or unsealed credential value appears anywhere in the log output

### Requirement: Key Rotation Invalidates Stored Credentials
The system MUST support rotating the sealed-box key pair, and rotating the private key MUST render all previously sealed credentials unusable, requiring affected users to re-submit credentials.

#### Scenario: Rotated key invalidates old data
- GIVEN sealed credentials created under key pair v1
- WHEN the private key is rotated to v2 without re-sealing existing data
- THEN the runner can no longer unseal the v1 sealed credentials
- AND affected users must re-enter credentials under the new public key
