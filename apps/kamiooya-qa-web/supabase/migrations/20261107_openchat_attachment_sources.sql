-- Member delivery uses the existing guarded attachment Edge; storage stays private.
-- A dedicated source per attachment avoids guessing a join to old MD-derived IDs.
alter table public.openchat_attachments
  add column if not exists source_context jsonb not null default '{}'::jsonb,
  add column if not exists source_log_id text generated always as ('oc_' || id) stored;
create unique index if not exists openchat_attachments_source_log_idx
  on public.openchat_attachments(source_log_id);

create or replace function public.sync_openchat_attachment_source()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
  ctx jsonb := new.source_context;
  stamp timestamptz;
  label text := coalesce(nullif(left(ctx->>'chat_title',300),''),'LINEオプチャ（ルーム名未取得）');
  body text;
begin
  begin stamp := nullif(ctx->>'posted_at','')::timestamptz;
  exception when others then stamp := null; end;
  body := '【LINE添付・内容未解析】' || E'\n' || label || E'\n'
    || new.original_name || E'\n' || coalesce(left(ctx->>'caption',4000),'');
  insert into public.line_openchat_logs as target
    (id,route_id,chat_title,chat_name,stream_type,thread_title,posted_at,post_date,
     sender_name,content,source_system,ingest_status,metadata)
  values (new.source_log_id, coalesce(nullif(left(ctx->>'route_id',128),''),'attachment'),
    label,label,case when new.thread_id='' then 'main' else 'thread' end,
    nullif(left(ctx->>'thread_title',300),''),stamp,(stamp at time zone 'Asia/Tokyo')::date,
    nullif(left(ctx->>'sender_name',200),''),body,'line_openchat_attachment','ready',
    jsonb_build_object('attachment_id',new.id,'attachment_kind',new.kind,'content_analyzed',false))
  on conflict (id) do update set
    route_id=excluded.route_id,chat_title=excluded.chat_title,chat_name=excluded.chat_name,
    stream_type=excluded.stream_type,thread_title=excluded.thread_title,
    posted_at=excluded.posted_at,post_date=excluded.post_date,sender_name=excluded.sender_name,
    content=excluded.content,metadata=excluded.metadata,
    embedding=case when target.content is distinct from excluded.content then null else target.embedding end,
    updated_at=now()
  where target.source_system='line_openchat_attachment';
  if not found then raise exception 'attachment_source_identity_conflict'; end if;
  return new;
end;
$$;
revoke all on function public.sync_openchat_attachment_source() from public,anon,authenticated;
drop trigger if exists openchat_attachment_source on public.openchat_attachments;
create trigger openchat_attachment_source after insert or update of source_context,original_name
  on public.openchat_attachments for each row execute function public.sync_openchat_attachment_source();

-- Metadata only: generate dedicated sources for existing backups. No media download.
update public.openchat_attachments set source_context=source_context;

create or replace view public.openchat_member_attachments
with (security_invoker=true) as
  select a.id,a.source_log_id,a.original_name,a.content_type,a.byte_size,a.bucket,a.storage_path
  from public.openchat_attachments a join public.line_openchat_logs s on s.id=a.source_log_id
  where s.ingest_status='ready' and s.source_system='line_openchat_attachment';
revoke all on public.openchat_member_attachments from public,anon,authenticated;
grant select on public.openchat_member_attachments to service_role;
