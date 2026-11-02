# OpenChat private attachment backup TASK

- executor: Codex
- status: implemented_offline_tested_live_validation_pending
- scope: independent attachment queue, bounded download, private Supabase storage, retry/dedup/capacity checks and tests
- acceptance: no AI calls; original MD sync independent; no duplicate original objects; fail closed on capacity uncertainty; video/audio supported within configured limits; no member-facing release
- exclusions: PR220 merge, publication, account changes, deletion of archived originals, external notification

Validation: 16 focused tests passed in the actual CHRLINE Python 3.9 runtime; 195 Python tests passed overall. Python compilation, shell syntax and diff checks passed. No real download, SQL migration, flag activation, schedule change or member-facing deployment performed. Live representative-file tests and private storage setup remain.
