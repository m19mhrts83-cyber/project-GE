begin;
set local lock_timeout='3s';
set local statement_timeout='30s';
-- Preserve unknown month/day; year inference is separate and auditable.
alter table public.comments add column if not exists inferred_year smallint check(inferred_year between 1900 and 2100);
alter table public.comments add column if not exists inferred_year_evidence jsonb;
with numeric_comments as (
 select comment_id,comment_id::bigint as numeric_id,posted_at,
 extract(year from posted_at at time zone 'Asia/Tokyo')::integer as known_year
 from public.comments where comment_id ~ '^[0-9]{1,15}$'
 and coalesce(source_type,'') not in ('__admin_meta__','__master_xfer__')
), bounds as (
 select *,max(known_year) over(order by numeric_id rows between unbounded preceding and 1 preceding) as lower_year,
 min(known_year) over(order by numeric_id desc rows between unbounded preceding and 1 preceding) as upper_year,
 max(numeric_id) filter(where posted_at is not null) over(order by numeric_id rows between unbounded preceding and 1 preceding) as lower_id,
 min(numeric_id) filter(where posted_at is not null) over(order by numeric_id desc rows between unbounded preceding and 1 preceding) as upper_id
 from numeric_comments
)
update public.comments c set inferred_year=b.lower_year,
 inferred_year_evidence=jsonb_build_object('method','monotonic_comment_id_bounds','lower_comment_id',b.lower_id::text,'upper_comment_id',b.upper_id::text,'year',b.lower_year,'verified_at',now())
from bounds b where c.comment_id=b.comment_id and c.posted_at is null and c.inferred_year is null
 and b.lower_year=b.upper_year and b.lower_year between 1900 and 2100;

create or replace function public.qa_reference_metadata()
returns jsonb language sql stable security definer set search_path=public,pg_temp as $$
 select jsonb_build_object(
  'comments',coalesce((select jsonb_agg(jsonb_build_object('comment_id',c.comment_id,'posted_at',c.posted_at,'inferred_year',c.inferred_year,'forum_category',c.forum_category))
    from public.comments c where c.comment_id not like 'admin_%' and coalesce(c.source_type,'') not in ('__admin_meta__','__master_xfer__')),'[]'::jsonb),
  'sources',coalesce((select jsonb_agg(jsonb_build_object('id',s.id,'source_key',s.source_key,'title',s.title,'video_url',s.video_url))
    from public.knowledge_sources s),'[]'::jsonb));
$$;
revoke all on function public.qa_reference_metadata() from public,anon,authenticated;
grant execute on function public.qa_reference_metadata() to service_role;
notify pgrst,'reload schema';

commit;
