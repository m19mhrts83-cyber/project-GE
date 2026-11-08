# Private OpenChat attachment backup

This candidate is independent of the member-viewing authentication PR. It does not enable member reads, alter the existing text-search publication flow, call AI services or copy binary attachments to OneDrive. Existing ingestion remains unchanged unless explicitly enabled.

## Components

- `line_unofficial_poc/openchat_attachments.py`: private SQLite queue, one identity per room/message, captured before MD dedup in batch/realtime collectors. Only required non-secret metadata is retained. Image, video, audio and file messages are supported; encrypted/chunked media is recorded as unsupported, never silently counted as saved.
- `scripts/jarvis_openchat_attachments.py`: single worker with the existing LINE session lock; bounded streaming download; content checks; resumable 6MiB TUS upload; SHA-256 verification before publishing private metadata; retry spool preserved on failure.
- Supabase migration: dedicated private bucket and metadata table, restrictive Storage policy for browser roles, RLS, service-role-only access and a project-wide usage RPC. No comment FK is assumed. The RPC fails closed if an object's size is unknown.
- Existing daily runner: an opt-in worker step runs while the realtime collector is paused. Attachment failure is logged separately and does not stop MD-to-DB ingestion or watcher recovery.

Content objects use `objects/<sha256>` so distinct messages can reference one original. Spool files live in a local nonsync directory with restrictive permissions, and only verified temporary copies are removed. Source/archived originals are never deleted. Redirects carrying LINE/Supabase credentials are forbidden. Secrets, response bodies and signed URLs are not logged.

## Limits and operational prerequisites

The default queue capture and worker are OFF. Default worker invocation prints local status only, without LINE login or remote requests. It may initialize local queue files.

The migration is NOT applied by the script. Before enabling, apply/review it for the designated project and check the bucket remains private, browser roles cannot read objects/metadata, the usage RPC is available, the global Storage upload limit permits the chosen per-file limit, and remaining organization storage/transfer allowances are sufficient. Do not increase limits or enable anonymous policies to work around errors.

The candidate accepts at most 500MiB per file, uses at most 2GiB of local media spool, and holds new transfers if project-wide stored bytes plus a conservative reservation would exceed 80GB. These are application safety settings, not guaranteed billing limits. Usage checks do not atomically reserve capacity against unrelated writers or cover additional projects in the organization. Concurrent non-worker storage changes and transfer allowance still need operational monitoring. Verification downloads consume egress; no promise of unlimited free storage/transfer is made.

No real LINE/Supabase transfer or production schedule change is implied by offline tests. The raw Square download path follows the installed CHRLINE non-E2EE implementation; actual image/file/video/audio examples still need verification, including original versus preview identity. Albums, notes, stickers and external file-sharing links are not claimed as covered. Expired/unsupported/invalid/capacity-held attachments remain visible in the status counts. Historical recovery is limited to messages still retrievable from LINE. MD already ingested without raw metadata is not sufficient to reconstruct every old attachment automatically.

## Enable after review and representative-file validation

Use the already configured Mac runtime and project-specific server credentials. Never use the personal Dashboard project's credentials for file storage. Supply secrets through existing private environment mechanisms, never command-line literals or repository files.

1. Apply the reviewed migration and verify access/capacity conditions above. Establish the global upload limit separately; the migration does not change it.
2. Set `LINE_OPENCHAT_ATTACHMENTS_QUEUE=1` in the existing collector's environment. The default cohort is `backfill`; keep that for initial historical collection so it does not inflate daily growth predictions. Avoid competing LINE clients or an extra realtime daemon.
3. With the existing watcher safely paused by the normal runner, test a small worker batch using `--apply --limit 4`. The worker never starts QR login or pauses a watcher on its own; a busy session returns 75.
4. Inspect source/file identity, formats, SHA-256, private access, saved/error counts and bytes. Only after that enable `LINE_OPENCHAT_ATTACHMENTS_APPLY=1` in the daily runner. Switch the capture cohort to `daily` for normal new-message collection. Explicit historical backfill should override it to `backfill`.
5. Status is available from the worker without `--apply`. Backfill bytes are separate from daily-growth bytes. Distinct hashes are counted once. A monthly growth estimate appears only after at least two observed days; it is a rough trend, not a cost promise. Use project/organization usage and current rates before operator discussions. Missing collection days lower confidence and require review. `--retry-held --apply` resumes capacity-held jobs after resolving the cause; it does not retry expired/unsupported cases automatically.

No new schedule is installed. Current daily scheduling remains managed by the existing runner. A Draft PR is a review boundary, not permission to merge, migrate, publish or change live accounts. This branch's Vercel Git deployments are disabled in the root and four app configurations.


## Operational overlay without merging the authentication branch

`jarvis_openchat_daily_runtime.py` runs the existing text runner first, then pauses the watcher, acquires the same LINE lock, scans with independent attachment cursors, saves pending files and resumes the watcher with a process check. It publishes only counters and status to the private Dashboard/work history. A pinned snapshot under a local nonsync runtime directory can be used by the existing daily LaunchAgent without editing the main checkout or merging either PR. Preserve the existing calendar intervals and save the original plist for rollback.

Real integration requires direct authenticated OBS GET for originals; the SDK's OA proxy may return empty bodies for files/video. Recent scans use BACKWARD=2 with the text collector's sync token as a read-only anchor, plus a separate history cursor. The scanner never writes text cursor state. Recent messages are checked every run while historical pagination continues. Previously expired files stay explicitly failed rather than counted as saved. Current operational worker/bucket limits are 50MiB when the spend cap restricts the global limit; do not disable the spend cap automatically.

The operational wrapper exposes `--scan-pages` and `--scan-threads` for a bounded one-off coverage check. These do not change the daily defaults or the calendar. Already unavailable source jobs are not retried. Report saved, unavailable and unvisited source ranges separately.

## Member delivery extension (2026-11-07)

The backup-only description above is the original release scope. The requested member delivery is specified in `kamiooya_openchat_member_attachments_TASK.md`: dedicated attachment source IDs, guarded metadata/signing via the existing Edge, filename search / attachment-only browse, and citation links. Apply `20261107_openchat_attachment_sources.sql` before deploying that Edge or installing the new metadata worker. Storage remains private. No guessed join to MD-derived message IDs, no binary re-download, OCR or media transcription. Existing weekly metadata embedding may index the dedicated sources; listing and filename browse make no AI calls. Deployment and live verification status belong in the task document.
