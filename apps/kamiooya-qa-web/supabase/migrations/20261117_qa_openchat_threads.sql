-- LINEオープンチャットのスレッドに、オプチャごとの通し番号を振る（2026-11-17 運営 目黒さん・木村さん要望）
-- 「どの投稿に対するスレッドか」を見分けやすくする。番号は一度振ったら変えない（新しいスレッドは続き番号）。
-- スレッドの見分けは line_openchat_logs.thread_title（名前、または「t013e392…」のような識別子の頭8文字）。
-- 画面と回答の根拠では「スレッド12」と、最初の書き込みの書き出しを見出しに使う。スイッチ openchat_threads。

create table if not exists public.qa_openchat_threads (
  chat_title text not null,
  thread_key text not null,
  thread_no integer not null,
  first_posted_at timestamptz,
  last_posted_at timestamptz,
  post_count integer not null default 0,
  first_sender text,
  first_snippet text,
  updated_at timestamptz not null default now(),
  primary key (chat_title, thread_key),
  unique (chat_title, thread_no)
);

alter table public.qa_openchat_threads enable row level security;
revoke all on public.qa_openchat_threads from public, anon, authenticated;
grant select, insert, update on public.qa_openchat_threads to service_role;

create index if not exists line_openchat_logs_chat_thread_idx
  on public.line_openchat_logs (chat_title, thread_title, posted_at)
  where stream_type = 'thread';

-- 取込のあとに呼ぶ。既存スレッドは件数・最終日時・見出しを更新、新しいスレッドに続き番号を振る。
create or replace function public.qa_refresh_openchat_threads()
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  added integer := 0;
begin
  create temporary table _oc_thread_stats on commit drop as
  with base as (
    select chat_title, thread_title as thread_key, posted_at, ingest_status, sender_name, content
    from line_openchat_logs
    where stream_type = 'thread'
      and coalesce(chat_title, '') <> ''
      and coalesce(thread_title, '') <> ''
  ),
  texts as (
    -- 見出し候補：添付・本文なしを除き、先頭のメンション（@講師きむら 等）を外した本文
    select chat_title, thread_key, posted_at, sender_name,
           btrim(regexp_replace(regexp_replace(content, '^(\s*@\S+)+', ''), '\s+', ' ', 'g')) as body
    from base
    where ingest_status = 'ready'
      and content not like '【LINE添付%'
      and content not like '[非テキスト%'
      and content not like '[本文なし%'
  ),
  firsts_any as (
    select distinct on (chat_title, thread_key) chat_title, thread_key, sender_name, body
    from texts
    order by chat_title, thread_key, posted_at asc nulls last
  ),
  firsts_good as (
    -- 挨拶・メンションだけの短い書き込みは飛ばし、中身のある最初の書き込みを見出しにする
    select distinct on (chat_title, thread_key) chat_title, thread_key, body
    from texts
    where char_length(body) >= 8
      and body !~ '^(こちらに|こちらで|よろしくお願い|宜しくお願い|ありがとうございま|お疲れ様|おつかれさま|承知しました|了解です)'
    order by chat_title, thread_key, posted_at asc nulls last
  ),
  firsts as (
    select a.chat_title, a.thread_key, a.sender_name as first_sender,
           left(coalesce(g.body, a.body), 120) as first_snippet
    from firsts_any a
    left join firsts_good g using (chat_title, thread_key)
  )
  select b.chat_title, b.thread_key,
         min(b.posted_at) as first_posted_at,
         max(b.posted_at) as last_posted_at,
         count(*) filter (where b.ingest_status = 'ready')::int as post_count,
         f.first_sender, f.first_snippet
  from base b
  left join firsts f using (chat_title, thread_key)
  group by b.chat_title, b.thread_key, f.first_sender, f.first_snippet;

  update qa_openchat_threads t
     set first_posted_at = least(t.first_posted_at, s.first_posted_at),
         last_posted_at = s.last_posted_at,
         post_count = s.post_count,
         first_sender = coalesce(s.first_sender, t.first_sender),
         first_snippet = coalesce(s.first_snippet, t.first_snippet),
         updated_at = now()
    from _oc_thread_stats s
   where t.chat_title = s.chat_title and t.thread_key = s.thread_key
     and (t.post_count is distinct from s.post_count
          or t.last_posted_at is distinct from s.last_posted_at
          or t.first_snippet is distinct from coalesce(s.first_snippet, t.first_snippet));

  with fresh as (
    select s.*
      from _oc_thread_stats s
     where not exists (
       select 1 from qa_openchat_threads t
        where t.chat_title = s.chat_title and t.thread_key = s.thread_key)
  ),
  numbered as (
    select f.*,
           coalesce((select max(t.thread_no) from qa_openchat_threads t where t.chat_title = f.chat_title), 0)
             + row_number() over (partition by f.chat_title order by f.first_posted_at asc nulls last, f.thread_key) as thread_no
      from fresh f
  )
  insert into qa_openchat_threads
    (chat_title, thread_key, thread_no, first_posted_at, last_posted_at, post_count, first_sender, first_snippet)
  select chat_title, thread_key, thread_no, first_posted_at, last_posted_at, post_count, first_sender, first_snippet
    from numbered;
  get diagnostics added = row_count;
  return added;
end;
$$;

revoke all on function public.qa_refresh_openchat_threads() from public, anon, authenticated;
grant execute on function public.qa_refresh_openchat_threads() to service_role;

select public.qa_refresh_openchat_threads();

insert into public.qa_feature_flags(feature, stage, owner_ids, reviewer_ids, note)
select 'openchat_threads', 'owner', owner_ids, reviewer_ids, 'LINEオプチャのスレッド番号（オプチャごとの通し番号・スレッドごとに読む）'
from public.qa_feature_flags where feature = 'ranking_themes'
on conflict (feature) do nothing;
