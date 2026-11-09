-- 下書きレビュー: 箇所ごとの声のダメ出しをその場で保存し、まとめて直しに回す（Mac の Cursor が処理）
-- jarvis-dashboard PJ（idkdqneutpvkhxhpjtgc）
--   pending_comments: まだ直しに回していないダメ出し（1件ごとに owner_decisions surface=draft_review action=comment にも残る）
--   revise_request:   { status: queued|running|done|error, base, comments[], requested_at, started_at, finished_at, error, engine }
--                     scripts/jarvis_draft_revise_worker.py（launchd/cursor_revise_worker_runner.sh・45秒ごと）が拾う

alter table public.draft_reviews
  add column if not exists pending_comments jsonb not null default '[]'::jsonb,
  add column if not exists revise_request jsonb;

create index if not exists draft_reviews_revise_queued_idx
  on public.draft_reviews ((revise_request ->> 'status'))
  where revise_request is not null;
