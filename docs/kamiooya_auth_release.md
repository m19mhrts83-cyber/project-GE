# Raimo authentication release

The authentication gateway keeps the existing Raimo member database and existing passwords. Browser-provided actor IDs cannot authorize operations. The gateway verifies credentials on the server, stores only token hashes in a private Supabase table, and checks current membership and credential version on every request. Shared rate limiting is backed by an atomic SQL function. Sessions last eight hours and logout removes the persisted session.

All legacy routes require server proof before any existing action. POST aliases for reads prevent placing that proof in URLs. New internal user/comment lookup routes are also guarded. Generic comment operations cannot mutate reserved administrative records; administrative records are excluded from community lists and related-comment retrieval. Bootstrap and secret-export routes stay inaccessible from the browser. Admin role changes cannot directly assign master privileges. Master transfer validation checks the named recipient and expiry on the server.

Registration hashes new passwords with bcrypt. Password-reset issuance creates the random token and expiry on the server, stores only its hash and sends only an application-origin URL. Legacy browser notification requests cannot override that URL. Existing users are not reset automatically. Notifications must not be triggered during verification with real member addresses.

Attachment tokens require the hash of an active parent login session. The attachment function checks this against the authentication gateway before issuing a 60-second object URL. Logging out or changing the password blocks further links; an already issued URL may remain valid for its remaining lifetime.

## Release order

1. Apply `20261104_raimo_auth_sessions.sql`; verify service-only table access and atomic throttling.
2. Configure the server-only gateway proof and existing attachment proxy secret. Never put these in Git, the browser, URL parameters or public logs.
3. Deploy `raimo-auth` with JWT verification disabled at the platform layer: the function verifies its own opaque sessions. Bundle the gateway and adapter or include their relative files.
4. Generate the guarded Raimo definition from the latest private export. Preserve existing runtime integrations. Compare the route inventory and retain a private backup. Never publish the raw unguarded template.
5. Install the guarded definition and activate the gateway URL in the frontend as one cutover. Verify existing-user login, direct-call denial, own-conversation access, staff permissions and logout. An incomplete cutover should fail closed; do not restore unguarded routes as a rollback.
6. Deploy the attachment handler pointing to the gateway status endpoint. Set `COMMUNITY_ATTACHMENTS_MEMBER_READS_ENABLED=1` only after the authentication chain has passed real integration verification. Old attachment tokens lacking a parent session remain invalid.
7. Verify the actual browser login-to-file flow and private storage controls, then merge the reviewed release. Update existing automation scripts together with the server proof configuration, including the root-checkout scripts used by scheduled jobs.

## Verification commands

```
node --experimental-strip-types --test apps/kamiooya-qa-web/tests/*.test.mjs
python -m unittest discover -s scripts/tests
npm --prefix apps/kamiooya-qa-web run build
npx deno check apps/kamiooya-qa-web/supabase/functions/raimo-auth/index.ts
```

Unit tests use synthetic users, transport and persistent-store responses. These tests do not replace live integration and browser verification. The private operational result and handoff identify the actual release state. Historical third-party access investigation is outside this change.
