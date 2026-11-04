# Authentication candidate history

This document described the original offline-only draft. The production adapter, shared session/throttling schema, guarded read aliases, credential/reset handling and automation transport were subsequently added. See [the release runbook](kamiooya_auth_release.md) for the current implementation and cutover requirements. Neither the existence of this code nor passing unit tests means that a production release has completed.

# Offline authentication candidate

Status: draft, not deployed, not ready for merge. No historical access-log investigation is part of this change.

## What this change does

The candidate gateway uses server-issued opaque sessions, current membership and role checks, conversation ownership checks, and public-field projections for user responses. Browser-supplied actor IDs, roles and internal secrets cannot establish authority. Unreviewed operations remain denied.

Attachment sessions can require a parent-session reference. A trusted status adapter must check that the parent session is active and belongs to the same user. Logging out, expiry and credential-version changes then block further attachment URL issuance. Previously issued signed URLs remain valid until their short expiry; this change does not revoke URLs already issued.

The offline definition generator puts a server-only proof check before every existing step of all 60 backend routes. It preserves maintenance stops. It does not upload definitions or replace the existing deployable template. The frontend gateway URL remains empty, and the deployed attachment-read hold remains false.

The root and four application Vercel configurations disable Git deployment for `codex/kamiooya-auth-offline-review`. This branch rule does not prevent manual deployment or a deployment after merging into another branch. Draft PR status also does not permanently prohibit merging. Do not merge or manually publish this candidate.

## Validation and limits

Tests exercise the actual frontend JavaScript login/API/logout handlers, the gateway, and the attachment handler with synthetic users, sessions and upstream responses. They cover invalid/expired sessions, rate limiting, current membership, changed roles and credential versions, other users' conversations, response projection, concurrent identities, URL issuance and logout revocation. These are offline functional tests, not browser-rendering tests, a real database integration test, a production security assessment or load testing.

Run:

```sh
node --experimental-strip-types --test apps/kamiooya-qa-web/tests/*.test.mjs
python -m unittest discover -s scripts/tests
```

## Required before integration

1. Implement the trusted production adapters for credential verification, persistent session storage, throttling, current membership/credential version, ownership and permitted backend calls. The injected interfaces and in-memory fixtures are not a production implementation.
2. Store session tokens securely, preferably hashed at rest. Session lookups by parent reference must verify expiry, user ownership and credential version. A multi-instance deployment needs shared storage and throttling, not process-local maps.
3. Install the guarded backend definitions atomically with the adapter and frontend cutover. The adapter alone cannot prevent direct access to legacy routes. Resolve placeholders server-side; never ship their actual values to the browser or source control. An unresolved placeholder must prevent publication.
4. Implement the trusted attachment status adapter returning `session_active` and pass the verified parent reference when issuing an attachment session. The existing status endpoint does not implement this contract yet. Keeping the read hold prevents accidental partial activation.
5. Review and implement registration, password recovery, delegated admin operations and other currently denied routes. The candidate deliberately does not claim full feature parity. Assess credential migration/rotation separately, without historical access analysis or automatic account changes.
6. In an isolated environment, verify real adapters, actual browser screens, failure/recovery and the complete login-to-file flow. Apply a new attachment signing key when explicitly authorized to release; do not reuse previous tokens.

Publication, changing live credentials and re-enabling attachment reads require a separate release decision. No deployed route imports the new gateway module in this draft.
