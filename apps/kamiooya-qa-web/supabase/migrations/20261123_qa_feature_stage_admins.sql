-- 段階公開スイッチに admins（管理者の役割の人全員）を足す（2026-11-23 松野さん「メールで名指しせず管理者権限の人に見せる」）。
alter table public.qa_feature_flags drop constraint if exists qa_feature_flags_stage_check;
alter table public.qa_feature_flags add constraint qa_feature_flags_stage_check check (stage in ('off','owner','reviewers','admins','all'));
