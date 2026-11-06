# Q&A search reliability and reference display

The auth gateway admits a persistent answer job and returns its identifier immediately. The existing approved membership, credential version and chat ownership checks apply to admission and every status read. Job tables/RPCs are service-only. A stable client request identifier and atomic admission serialize active jobs per user, so a lost response or repeated status request does not start another model call. A lost worker becomes an explicit timeout; it is not silently restarted with an uncertain generation outcome.

The processing budget is 300 seconds, with time reserved for persistence. Normal search uses the existing guarded Raimo route with a background deadline rather than the legacy one-minute HTTP relay. Semantic search executes the shared `semantic-search/handler.ts` implementation inside the background worker; it does not nest another synchronous Edge HTTP request. `EdgeRuntime.waitUntil` is still subject to the platform worker's lifetime/CPU/memory limits; validate actual deployment behavior rather than promising that every task has a fresh worker lifetime.

The browser polls through short authenticated requests, retains only the pending request/job identifiers and question in per-user session storage, and can resume delivery after reconnection or login. It stores no credentials there. Logout stops that browser's retrieval; subsequent retrieval requires a valid current approved session. An explicit retry following a terminal failure must not be confused with automatic deduplication of an in-flight request. When an upstream continues after a cancellation, inspect saved history before retrying.

## Reference identity and dates

Semantic context labels are generated before similarity/recency presentation sorting and returned on the corresponding source records. Reordering never renumbers them. The answer's source markers link to those exact records. Video references retain the title and each individual start time; Vimeo timestamps use `#t=...s` while preserving unlisted URL parameters. Never substitute a newly invented date for a missing publication/post date.

The UI groups community and LINE references by calendar year, newest first. The current JST calendar year is subdivided by month. Missing dates can be hydrated by exact comment ID from the service-only reference metadata endpoint, independently of the large legacy comment download.

The inspected legacy semantic deployment saved its answer-context ID order in recent search events. The owner-scoped history endpoint can recover that order for an unambiguous query and assistant timestamp match. Missing or ambiguous history is not assigned a guessed number. Referenced video chunks can be recovered from their recorded keys. This recovery is limited to the inspected recent protocol window; it does not rewrite old answer text or perform additional model generation.

`scripts/jarvis_qa_reference_date_repair.py` defaults to a dry run against an audited Raimo export. It validates source dates, holds conflicting IDs, repairs only null Supabase dates and records a private audit. Existing non-null dates, original content and ingestion timestamps are never overwritten. Do not commit or sync private source exports/reports.

## Attachment initialization

Read-only session/index loading retries bounded transient network/5xx failures. Authentication/permission errors are not retried. Page offsets must advance and records are published to the UI only after a complete index; stale login generations cannot overwrite a newer user. A visible retry control replaces the previous one-shot error toast. Passwords are not kept for retry. The existing private Storage and per-request membership checks remain unchanged.

## Deployment order

1. Apply `20261106_reference_metadata.sql` and `20261106_answer_jobs.sql`; verify anonymous denial and service access.
2. Audit and conditionally apply the missing-date repair from a private canonical export. Record counts and source assumptions.
3. Bundle and deploy `raimo-auth` with external npm/HTTPS imports, then the shared semantic entry point. Preserve existing environment values and the previous code for rollback. No new key or paid service is required.
4. Publish the matched frontend HTML/JS and existing catalog prefix, setting the verified auth-gateway URL. Preserve the business source's existing reference-filter/navigation features. A frontend source change alone does not update the live Raimo app.
5. Validate real normal and semantic answers, exact source-label links, chronological groups, per-position video URLs, attachment index/open, anonymous denial and logout. Synthetic clocks are useful regression tests, not evidence of real multi-minute worker execution. Keep unresolved real-role and next daily-operation checks explicit.

Test entrypoints: Node tests under `apps/kamiooya-qa-web/tests`, Deno check for both Edge entry points, and the date-repair Python tests.

## Bounded and on-demand reference reads

The legacy Raimo comment response was about 70 MB on the wire and could exhaust the gateway's compute resources (HTTP 546). A server-proof-protected `POST /internal/read/comments-page` reads at most 500 rows by an ascending numeric primary-key cursor. The approved-member gateway validates the cursor, fixes the upstream route and hard page size, and projects display fields, omitting email/IP/user-agent and internal credentials. `scripts/jarvis_qa_comment_pages.py` prepares this one additive alias from the current private live definition, preserving all original routes and guards. Never commit its private input/output definitions.

The client publishes a complete, cursor-validated list only after successful paging. It loads comments/lesson descriptions and full video chunks on first opening their corresponding views, shares an in-flight read, caches for that login, and clears on logout. Q&A uses compact reference metadata and returned answer sources without downloading both full reference datasets at login.

## Year-only inference and cited-source priority

`20261106_reference_years.sql` leaves `posted_at` unchanged and records only `inferred_year` plus bound-comment evidence. A numeric missing-date comment is inferred only when the maximum known year below its ID equals the minimum known year above it. Use prefix window aggregates in opposite sort directions, bounded lock/statement timeouts and an atomic transaction. The audited 140 remaining source comments all satisfy these bounds for 2026; month/day remain unknown. Videos and lesson descriptions are never grouped by inferred dates.

Answer markers have a compact source index at the top in first-mention order, with dates for comments/LINE and title/position playback for videos. Detailed comment and LINE references remain newest first by calendar year/current-year month. Stable context labels do not change when their display order changes.

## Release verification checkpoint (2026-11-06)

PR #238. Missing exact dates repaired: 22,339; dated Supabase rows: 25,652. Year-only records: 140, actual timestamps still null. Service metadata succeeds, anonymous access denied. Two concurrent identical DB admissions create one job, without any model invocation. Real normal searches completed in 40.46 and 76.60 seconds; the latter survived a browser reload/re-login and delivered the same saved answer with no extra job. Community view displayed 25,522 source rows, and its authenticated original-image link opened a 2911×3024 private Storage object. Semantic search and the final on-demand UI version still require the release's final live check; do not treat synthetic 90/140/240-second tests as those live checks.
