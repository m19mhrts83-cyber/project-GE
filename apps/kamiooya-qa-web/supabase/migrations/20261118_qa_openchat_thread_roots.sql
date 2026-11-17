-- オプチャのスレッドに「元の投稿」（スレッドを始めたメイン投稿）を結び付ける（2026-11-18）
-- 運営（目黒さん・木村さん）要望「どの投稿に対するスレッドか分かるように」。木村さんは特に物件名の履歴を重視。
-- 元投稿は LINE の getSquareThread(includeRootMessage) で取得（line_unofficial_poc/chrline_openchat_thread_roots.py）。
-- ここでは受け取った元投稿を qa_openchat_threads に書き、DB のメイン投稿（line_openchat_logs）と
-- 「オプチャ名＋日時（前後2分）＋本文の書き出し」で照合して root_log_id を入れる。
-- スイッチ openchat_threads（松野さんだけ）のまま。表示側は root_* が無くても従来どおり動く。

alter table public.qa_openchat_threads
  add column if not exists thread_mid text,
  add column if not exists root_message_id text,
  add column if not exists root_posted_at timestamptz,
  add column if not exists root_sender text,
  add column if not exists root_text text,
  add column if not exists root_log_id text,
  add column if not exists root_status text,
  add column if not exists root_fetched_at timestamptz;

comment on column public.qa_openchat_threads.root_status is
  'matched=DBのメイン投稿と一致 / line_only=LINEから本文のみ / deleted=LINE側でスレッド削除 / no_root=元投稿なし';

create index if not exists qa_openchat_threads_root_log_idx
  on public.qa_openchat_threads (root_log_id) where root_log_id is not null;

-- 照合用の正規化（空白を除き、先頭のメンション・[relatedMessageId] 行を外す）
create or replace function public.qa_openchat_norm_head(t text, n integer default 20)
returns text
language sql
immutable
as $$
  select left(
    regexp_replace(
      regexp_replace(
        regexp_replace(coalesce(t, ''), '^\[relatedMessageId\][^\n]*\n+', ''),
        '^(\s*@\S+)+', ''),
      '\s+', '', 'g'),
    n)
$$;

-- p: [{chat_title, thread_keys:[...], title, thread_mid, root_message_id, root_posted_at, root_text, status, fetched_at}]
-- 戻り値: 書き込んだスレッド数
create or replace function public.qa_apply_openchat_thread_roots(p jsonb)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  r jsonb;
  t_key text;
  t_chat text;
  v_status text;
  v_text text;
  v_at timestamptz;
  v_log_id text;
  v_log_sender text;
  n integer := 0;
begin
  for r in select * from jsonb_array_elements(coalesce(p, '[]'::jsonb)) loop
    t_chat := r->>'chat_title';
    v_status := coalesce(r->>'status', 'ok');
    v_text := nullif(btrim(coalesce(r->>'root_text', '')), '');
    v_at := nullif(r->>'root_posted_at', '')::timestamptz;

    -- スレッドを探す: 識別子・名前の完全一致 → 名前の書き出し一致
    select t.thread_key into t_key
      from qa_openchat_threads t
     where t.chat_title = t_chat
       and t.thread_key in (select jsonb_array_elements_text(coalesce(r->'thread_keys', '[]'::jsonb)))
     limit 1;
    if t_key is null and coalesce(r->>'title', '') <> '' and char_length(r->>'title') >= 8 then
      select t.thread_key into t_key
        from qa_openchat_threads t
       where t.chat_title = t_chat
         and t.thread_key like '「' || replace(replace(left(r->>'title', 15), '%', '\%'), '_', '\_') || '%'
       order by t.thread_no
       limit 1;
    end if;
    continue when t_key is null;

    v_log_id := null;
    v_log_sender := null;
    if v_status = 'ok' and v_at is not null then
      -- 本文の書き出しが一致するメイン投稿（日時が近い順）
      if v_text is not null then
        select l.id, l.sender_name into v_log_id, v_log_sender
          from line_openchat_logs l
         where l.chat_title = t_chat
           and l.stream_type = 'main'
           and l.posted_at between v_at - interval '2 minutes' and v_at + interval '2 minutes'
           and qa_openchat_norm_head(l.content) = qa_openchat_norm_head(v_text)
           and qa_openchat_norm_head(v_text) <> ''
         order by abs(extract(epoch from (l.posted_at - v_at)))
         limit 1;
      end if;
      -- 本文なし（画像など）の元投稿は、同じ分のメイン投稿が1件だけのときに限り結ぶ
      if v_log_id is null and v_text is null then
        select min(l.id), min(l.sender_name) into v_log_id, v_log_sender
          from line_openchat_logs l
         where l.chat_title = t_chat
           and l.stream_type = 'main'
           and date_trunc('minute', l.posted_at) = date_trunc('minute', v_at)
        having count(*) = 1;
      end if;
    end if;

    update qa_openchat_threads t
       set thread_mid = coalesce(nullif(r->>'thread_mid', ''), t.thread_mid),
           root_message_id = coalesce(nullif(r->>'root_message_id', ''), t.root_message_id),
           root_posted_at = coalesce(v_at, t.root_posted_at),
           root_text = coalesce(v_text, t.root_text),
           root_log_id = coalesce(v_log_id, t.root_log_id),
           root_sender = coalesce(v_log_sender, t.root_sender),
           root_status = case
             when coalesce(v_log_id, t.root_log_id) is not null then 'matched'
             when v_status = 'ok' and (v_text is not null or t.root_text is not null) then 'line_only'
             when v_status = 'ok' then coalesce(t.root_status, 'no_root')
             else v_status end,
           root_fetched_at = coalesce(nullif(r->>'fetched_at', '')::timestamptz, now()),
           updated_at = now()
     where t.chat_title = t_chat and t.thread_key = t_key;
    n := n + 1;
  end loop;
  return n;
end;
$$;

revoke all on function public.qa_apply_openchat_thread_roots(jsonb) from public, anon, authenticated;
grant execute on function public.qa_apply_openchat_thread_roots(jsonb) to service_role;
