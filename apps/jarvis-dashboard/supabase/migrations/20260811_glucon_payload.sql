-- glucon_report_drafts: 成果報告の対話型フロー用 payload
-- facts / clarify / consult / phase / result_candidates を保持

alter table public.glucon_report_drafts
  add column if not exists payload jsonb not null default '{}'::jsonb;

comment on column public.glucon_report_drafts.payload is
  '成果報告フロー: phase, facts, clarify, consult, result_candidates 等';
