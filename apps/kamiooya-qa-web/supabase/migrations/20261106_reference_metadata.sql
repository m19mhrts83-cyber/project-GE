-- Dates are repaired only from an audited source export, never from ingestion timestamps.
create or replace function public.qa_repair_missing_reference_dates(records jsonb)
returns integer language plpgsql security definer set search_path=public,pg_temp as $$
declare affected integer;
begin
 if jsonb_typeof(records)<>'array' or jsonb_array_length(records)>500 then raise exception 'invalid_batch'; end if;
 update public.comments c set posted_at=x.posted_at::timestamptz
 from jsonb_to_recordset(records) as x(comment_id text,posted_at text)
 where c.comment_id=x.comment_id and c.posted_at is null and x.posted_at is not null
 and c.comment_id not like 'admin_%' and coalesce(c.source_type,'') not in ('__admin_meta__','__master_xfer__');
 get diagnostics affected=row_count;
 return affected;
end $$;
revoke all on function public.qa_repair_missing_reference_dates(jsonb) from public,anon,authenticated;
grant execute on function public.qa_repair_missing_reference_dates(jsonb) to service_role;

create or replace function public.qa_reference_metadata()
returns jsonb language sql stable security definer set search_path=public,pg_temp as $$
 select jsonb_build_object(
  'comments',coalesce((select jsonb_agg(jsonb_build_object('comment_id',c.comment_id,'posted_at',c.posted_at,'forum_category',c.forum_category))
    from public.comments c where c.comment_id not like 'admin_%' and coalesce(c.source_type,'') not in ('__admin_meta__','__master_xfer__')),'[]'::jsonb),
  'sources',coalesce((select jsonb_agg(jsonb_build_object('id',s.id,'source_key',s.source_key,'title',s.title,'video_url',s.video_url))
    from public.knowledge_sources s),'[]'::jsonb));
$$;
revoke all on function public.qa_reference_metadata() from public,anon,authenticated;
grant execute on function public.qa_reference_metadata() to service_role;
notify pgrst,'reload schema';
