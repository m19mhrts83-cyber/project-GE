-- (4) の拡張: LINEオープンチャットの質問ランキング（2026-11-16）。追加のみ・既存テーブルには触れない。
-- 松野さん 11/15「アプリの中の質問以外でも、LINEオープンチャットで答えることが多い。どのオープンチャットで
-- どういう類似の質問が多かったかをランキングで」。
-- 仕組み: 週1回 GitHub Actions（course-theme-weekly.yml）が qa_openchat_question_digest() で質問らしい投稿だけを
-- DB の中で選んで受け取り、Gemini は「同じ趣旨のまとめ方」だけを返す。件数・人数・返信数はスクリプトが数える。
-- 結果は qa_openchat_rankings に入れ、運営分析（スイッチ openchat_ranking）で見る。
-- 投稿者の名前は外へ出さない（人数はハッシュで重複なしに数えるだけ）。読み書きは service_role だけ。

create table if not exists public.qa_openchat_rankings (
  id text primary key check (id ~ '^r[0-9]{8}[a-z0-9_-]{0,20}$'),
  created_at timestamptz not null default now(),
  period_days int not null default 120,
  model text not null default '',
  ranking jsonb not null default '[]'::jsonb,   -- [{topic, count, people, replies, recent, chats:[{chat,n}], examples:[{chat,d,text}]}]
  by_chat jsonb not null default '[]'::jsonb,   -- [{chat, questions, people, top:[{topic,count,people,examples[]}]}]
  stats jsonb not null default '{}'::jsonb      -- {posts, questions, people, chats}
);
alter table public.qa_openchat_rankings enable row level security;
revoke all on public.qa_openchat_rankings from public, anon, authenticated;
grant select, insert, update on public.qa_openchat_rankings to service_role;

-- 質問らしい投稿だけを DB の中で選ぶ（120日で 3,000 件前後・数百KB。全件は外へ出さない）。
-- 除くもの: 添付だけの投稿、URL だけの投稿、サポート担当・物件紹介担当・運営・社員・管理人の投稿、
--          お知らせ用の「01運営より全体周知」と動画紹介の「03 YouTube集中学習」。
-- replies: 同じスレッドの他の投稿の数（スレッドの中の質問だけ。メインの投稿は 0）。
create or replace function public.qa_openchat_question_digest(p_days int default 120)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
with
since as (select (now() - make_interval(days => greatest(7, least(coalesce(p_days,120), 365))))::date as d),
base as (
  select o.id, o.chat_title, o.stream_type, o.thread_title, o.post_date, o.sender_name, o.content
  from line_openchat_logs o, since
  where o.post_date >= since.d
    and o.chat_title !~ '^(01運営より全体周知|03 ?YouTube集中学習)'
),
th as (
  select chat_title, thread_title, count(*) as n
  from base where coalesce(thread_title,'') like '「t%' group by 1, 2
),
q as (
  select b.id, b.chat_title, b.post_date, b.sender_name, b.thread_title,
         left(regexp_replace(regexp_replace(b.content, '^\[relatedMessageId\]\s*[0-9]+\s*', ''), '\s+', ' ', 'g'), 160) as text
  from base b
  where b.content !~ '^【LINE添付'
    and b.content !~ '^\s*https?://\S+\s*$'
    and coalesce(b.sender_name,'') !~ '【(サポート|物件紹介|運営|社員)|\[管理人\]'
    and char_length(b.content) between 12 and 3000
    and b.content ~ '[？?]|教えて|でしょうか|ますか|ご存知|ご存じ|おすすめ|オススメ|分かる方|わかる方|どうすれば|どうしたら|悩んで'
)
select jsonb_build_object(
  'generated_at', now(),
  'period_days', greatest(7, least(coalesce(p_days,120), 365)),
  'posts', (select count(*) from base),
  'by_chat', coalesce((select jsonb_agg(jsonb_build_object('chat',c,'n',n) order by n desc) from
      (select chat_title c, count(*) n from base group by 1) x), '[]'::jsonb),
  'questions', coalesce((select jsonb_agg(jsonb_build_object(
      'chat', q.chat_title, 'd', q.post_date::text,
      'u', case when coalesce(q.sender_name,'') = '' then '' else left(md5(q.sender_name), 12) end,
      'r', coalesce(case when coalesce(q.thread_title,'') like '「t%' then th.n - 1 end, 0),
      'text', q.text) order by q.chat_title, q.post_date desc, q.id)
    from q left join th on th.chat_title = q.chat_title and th.thread_title = q.thread_title), '[]'::jsonb)
);
$$;
revoke all on function public.qa_openchat_question_digest(int) from public, anon, authenticated;
grant execute on function public.qa_openchat_question_digest(int) to service_role;

-- 段階公開スイッチ。まず松野さんだけ（ranking_themes と同じ名指し）。
insert into public.qa_feature_flags(feature, stage, owner_ids, reviewer_ids, note)
select 'openchat_ranking', 'owner', owner_ids, reviewer_ids, '(4) LINEオープンチャットの質問ランキング（運営分析）'
from public.qa_feature_flags where feature = 'ranking_themes'
on conflict (feature) do nothing;
