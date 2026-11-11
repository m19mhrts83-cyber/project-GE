-- (4) 質問ランキング＋講座テーマ提案（2026-11-11）。追加のみ・既存テーブルには触れない。
-- 仕組み（ループウェア）: 週1回 GitHub Actions が qa_theme_source_digest() の小さな集計を読み、
-- Gemini で「似た質問のまとまりランキング」と「講座テーマ案5つ」を作って qa_theme_rounds に入れる。
-- 運営分析で 採用／直して採用／不採用＋理由 を残し（qa_theme_decisions）、次の回はその判断を読んで案を作る。
-- 読み書きは service_role（raimo-auth 関数と週次の Actions）だけ。投稿者の名前・メールは集計に含めない。

create table if not exists public.qa_theme_rounds (
  id text primary key check (id ~ '^r[0-9]{8}[a-z0-9_-]{0,20}$'),
  created_at timestamptz not null default now(),
  period_days int not null default 120,
  model text not null default '',
  ranking jsonb not null default '[]'::jsonb,   -- [{topic, count, chatbot, forum, openchat, examples[]}]
  themes jsonb not null default '[]'::jsonb,    -- [{id, title, why, evidence, format, target}]
  stats jsonb not null default '{}'::jsonb      -- 件数の目安（チャットボット質問数など）
);
alter table public.qa_theme_rounds enable row level security;
revoke all on public.qa_theme_rounds from public, anon, authenticated;
grant select, insert, update on public.qa_theme_rounds to service_role;

create table if not exists public.qa_theme_decisions (
  round_id text not null references public.qa_theme_rounds(id) on delete cascade,
  theme_id text not null check (theme_id ~ '^t[0-9]{1,2}$'),
  choice text not null check (choice in ('adopt','revise','reject')),
  revised_title text not null default '' check (char_length(revised_title) <= 200),
  reason text not null default '' check (char_length(reason) <= 1000),
  decided_by text not null default '',
  decided_at timestamptz not null default now(),
  primary key (round_id, theme_id)
);
alter table public.qa_theme_decisions enable row level security;
revoke all on public.qa_theme_decisions from public, anon, authenticated;
grant select, insert, update on public.qa_theme_decisions to service_role;

-- 週次の材料。全件を外へ出さず、DB の中で数えて小さく（百KB前後）して返す（無料プランの通信量対策）。
create or replace function public.qa_theme_source_digest(p_days int default 120)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
with
since as (select now() - make_interval(days => greatest(7, least(coalesce(p_days,120), 365))) as t),
ev as (
  select lower(regexp_replace(btrim(query_text), '\s+', ' ', 'g')) as q,
         coalesce(comment_hit_count,0) + coalesce(chunk_hit_count,0) as hits, result_status, user_id
  from app_qa_search_events, since
  where created_at >= since.t and coalesce(btrim(query_text),'') <> ''
),
ev_top as (
  select left(q,120) as q, count(*) as n, count(*) filter (where hits = 0 and result_status = 'ok') as zero
  from ev group by q order by count(*) desc, q limit 200
),
cm as (
  select forum_category, topic_title, posted_at, content
  from comments, since
  where posted_at >= since.t and coalesce(is_deleted,false) = false
    and coalesce(comment_id,'') not like 'admin\_%'
    and coalesce(source_type,'') not in ('__admin_meta__','__master_xfer__')
),
cm_q as (
  select coalesce(forum_category,'') as cat, to_char(posted_at,'YYYY-MM') as d,
         left(regexp_replace(content, '\s+', ' ', 'g'), 140) as text
  from cm
  where content ~ '[？?]|教えて|悩'
  order by posted_at desc limit 250
),
oc as (
  select chat_title, thread_title, post_date, is_repair_related, repair_category, content
  from line_openchat_logs, since where post_date >= since.t::date
),
oc_q as (
  select coalesce(chat_title,'') as chat, post_date::text as d,
         left(regexp_replace(content, '\s+', ' ', 'g'), 140) as text
  from oc where content ~ '[？?]' order by post_date desc limit 200
)
select jsonb_build_object(
  'generated_at', now(),
  'period_days', greatest(7, least(coalesce(p_days,120), 365)),
  'chatbot', jsonb_build_object(
     'events', (select count(*) from ev),
     'users', (select count(distinct user_id) from ev),
     'top', coalesce((select jsonb_agg(jsonb_build_object('q',q,'n',n,'zero',zero)) from ev_top), '[]'::jsonb)),
  'forum', jsonb_build_object(
     'posts', (select count(*) from cm),
     'categories', coalesce((select jsonb_agg(jsonb_build_object('cat',c,'n',n) order by n desc) from
        (select coalesce(forum_category,'(なし)') c, count(*) n from cm group by 1) x), '[]'::jsonb),
     'topics', coalesce((select jsonb_agg(jsonb_build_object('cat',c,'topic',t,'n',n) order by n desc) from
        (select coalesce(forum_category,'') c, left(regexp_replace(coalesce(topic_title,''),'\s+',' ','g'),100) t, count(*) n
           from cm where coalesce(topic_title,'') <> '' group by 1,2 order by 3 desc limit 120) x), '[]'::jsonb),
     'questions', coalesce((select jsonb_agg(to_jsonb(cm_q)) from cm_q), '[]'::jsonb)),
  'openchat', jsonb_build_object(
     'posts', (select count(*) from oc),
     'by_chat', coalesce((select jsonb_agg(jsonb_build_object('chat',c,'n',n) order by n desc) from
        (select coalesce(chat_title,'') c, count(*) n from oc group by 1) x), '[]'::jsonb),
     'repair', coalesce((select jsonb_agg(jsonb_build_object('cat',c,'n',n) order by n desc) from
        (select coalesce(repair_category,'(なし)') c, count(*) n from oc where is_repair_related group by 1) x), '[]'::jsonb),
     'threads', coalesce((select jsonb_agg(jsonb_build_object('t',t,'n',n) order by n desc) from
        (select left(regexp_replace(thread_title,'\s+',' ','g'),80) t, count(*) n from oc
           where coalesce(thread_title,'') <> '' group by 1 order by 2 desc limit 60) x), '[]'::jsonb),
     'questions', coalesce((select jsonb_agg(to_jsonb(oc_q)) from oc_q), '[]'::jsonb)),
  'courses', jsonb_build_object(
     'total', (select count(*) from knowledge_sources),
     'titles', coalesce((select jsonb_agg(jsonb_build_object('title',left(title,90),'pub',to_char(published_at,'YYYY-MM')) order by published_at desc nulls last)
        from knowledge_sources where coalesce(title,'') <> ''), '[]'::jsonb))
);
$$;
revoke all on function public.qa_theme_source_digest(int) from public, anon, authenticated;
grant execute on function public.qa_theme_source_digest(int) to service_role;

insert into public.qa_feature_flags (feature, note) values
  ('ranking_themes', '(4) 質問ランキング＋講座テーマ提案（運営分析）')
on conflict (feature) do nothing;
