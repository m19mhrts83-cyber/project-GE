-- 添付の窓口（community-attachments）でも、意味検索・一覧と同じく、見られる人を限るオプチャを絞れるようにする。
-- 判定に使うルームの情報（route_id・chat_title・chat_name）を view の末尾に足すだけ。権限は変えない（service_role だけ）。
-- 当てる順: この migration → community-attachments の deploy（逆だと添付一覧が 503 になる。見えすぎる側には倒れない）。
create or replace view public.openchat_member_attachments
with (security_invoker=true) as
  select a.id,a.source_log_id,a.original_name,a.content_type,a.byte_size,a.bucket,a.storage_path,
    s.route_id,s.chat_title,s.chat_name
  from public.openchat_attachments a join public.line_openchat_logs s on s.id=a.source_log_id
  where s.ingest_status='ready' and s.source_system='line_openchat_attachment';
revoke all on public.openchat_member_attachments from public,anon,authenticated;
grant select on public.openchat_member_attachments to service_role;
