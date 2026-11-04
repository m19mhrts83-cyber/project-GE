# OpenChat private attachment backup TASK

- executor: Codex
- status: live_backup_verified_daily_overlay_enabled
- scope: independent attachment queue, bounded download, private Supabase storage, retry/dedup/capacity checks and tests
- acceptance: no AI calls; original MD sync independent; no duplicate original objects; fail closed on capacity uncertainty; video/audio supported within configured limits; no member-facing release
- exclusions: PR220 merge, publication, account changes, deletion of archived originals, external notification

Validation: 16 focused tests passed in the actual CHRLINE Python 3.9 runtime; 195 Python tests passed overall. Python compilation, shell syntax and diff checks passed. No real download, SQL migration, flag activation, schedule change or member-facing deployment performed. Live representative-file tests and private storage setup remain.

Live validation authorized by owner: private backup migration/settings and daily integration allowed; PR220 merge/member publication still prohibited. Current spend cap restricts global file size to 50MB; preserve spend cap, use 50MiB bucket/worker limit and report oversize files.

The existing daily LaunchAgent can use a pinned private-backup overlay while preserving the text runner and calendar. Rollback uses the saved original plist. Private storage settings and sample transfers have been verified; unavailable source attachments remain explicitly incomplete. Member access remains off.
