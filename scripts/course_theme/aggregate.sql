-- 講座テーマ提案ループウェア（試作）: DB内で集計し、1行のJSONだけ返す。
-- 会員名・メール・セッションIDは返さない。本文は先頭だけに切り詰める。
with
ev as (
  select created_at, lower(regexp_replace(btrim(query_text), '\s+', ' ', 'g')) as q,
         coalesce(comment_hit_count,0) + coalesce(chunk_hit_count,0) as hits,
         result_status, user_id
  from public.app_qa_search_events
  where query_text <> '' and created_at >= now() - interval '120 days'
),
ev_summary as (
  select jsonb_build_object(
    'events', count(*), 'users', count(distinct user_id),
    'first', min(created_at), 'last', max(created_at),
    'zero_hit', count(*) filter (where hits = 0 and result_status = 'ok')) as v
  from ev
),
top_q as (
  select coalesce(jsonb_agg(jsonb_build_object('q', left(q, 120), 'n', n, 'zero', zero) order by n desc), '[]') as v
  from (select q, count(*) n, count(*) filter (where hits = 0) zero
        from ev group by q order by count(*) desc limit 250) t
),
weekly as (
  select coalesce(jsonb_agg(jsonb_build_object('week', w, 'n', n) order by w), '[]') as v
  from (select to_char(date_trunc('week', created_at at time zone 'Asia/Tokyo'), 'YYYY-MM-DD') w, count(*) n
        from ev group by 1) t
),
cm as (
  select forum_category, topic_title, posted_at, content
  from public.comments
),
cat_all as (
  select coalesce(jsonb_agg(jsonb_build_object('cat', c, 'n', n, 'n180', n180) order by n desc), '[]') as v
  from (select coalesce(forum_category, '(なし)') c, count(*) n,
               count(*) filter (where posted_at >= now() - interval '180 days') n180
        from cm group by 1) t
),
topics as (
  select coalesce(jsonb_agg(jsonb_build_object('cat', c, 'topic', left(t, 100), 'n', n) order by n desc), '[]') as v
  from (select coalesce(forum_category, '') c, coalesce(topic_title, '') t, count(*) n
        from cm where posted_at >= now() - interval '180 days'
        group by 1, 2 order by count(*) desc limit 200) x
),
question_like as (
  select coalesce(jsonb_agg(jsonb_build_object('cat', c, 'd', d, 'text', txt) order by d desc), '[]') as v
  from (select coalesce(forum_category, '') c, to_char(posted_at, 'YYYY-MM') d,
               left(regexp_replace(content, '\s+', ' ', 'g'), 140) txt
        from cm
        where posted_at >= now() - interval '120 days'
          and (content like '%？%' or content like '%?%' or content like '%教えて%' or content like '%悩%' or content like '%どう%')
          and length(content) between 20 and 2000
        order by posted_at desc limit 300) x
),
oc as (
  select chat_title, thread_title, post_date, is_repair_related, repair_category, content
  from public.line_openchat_logs
  where post_date >= (now() - interval '120 days')::date
),
oc_summary as (
  select jsonb_build_object(
    'posts', (select count(*) from oc),
    'by_chat', (select coalesce(jsonb_agg(jsonb_build_object('chat', chat_title, 'n', n) order by n desc), '[]')
                from (select chat_title, count(*) n from oc group by 1) a),
    'repair_cat', (select coalesce(jsonb_agg(jsonb_build_object('cat', repair_category, 'n', n) order by n desc), '[]')
                   from (select coalesce(repair_category, '(なし)') repair_category, count(*) n from oc where is_repair_related group by 1) b),
    'threads', (select coalesce(jsonb_agg(jsonb_build_object('t', left(thread_title, 80), 'n', n) order by n desc), '[]')
                from (select thread_title, count(*) n from oc where coalesce(thread_title, '') <> '' group by 1 order by 2 desc limit 80) c),
    'question_like', (select coalesce(jsonb_agg(jsonb_build_object('chat', chat_title, 'd', post_date, 'text', txt)), '[]')
                      from (select chat_title, post_date, left(regexp_replace(content, '\s+', ' ', 'g'), 140) txt
                            from oc where (content like '%？%' or content like '%?%') and length(content) between 20 and 1500
                            order by post_date desc limit 200) d)
  ) as v
),
ks as (
  select coalesce(jsonb_agg(jsonb_build_object('title', left(title, 100), 'instructor', instructor, 'pub', to_char(published_at, 'YYYY-MM')) order by published_at desc nulls last), '[]') as v
  from public.knowledge_sources
)
select jsonb_build_object(
  'generated_at', now(),
  'search', (select v from ev_summary),
  'search_weekly', (select v from weekly),
  'search_top', (select v from top_q),
  'comment_categories', (select v from cat_all),
  'comment_topics_180d', (select v from topics),
  'comment_questions_120d', (select v from question_like),
  'openchat_120d', (select v from oc_summary),
  'knowledge_sources', (select v from ks)
) as result;
