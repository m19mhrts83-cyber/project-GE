-- 改善機能の段階公開スイッチ（2026-11-10）。追加のみ・既存テーブルには触れない。
-- stage: off=誰にも出さない / owner=owner_ids の人だけ / reviewers=owner_ids と reviewer_ids / all=会員全員
-- owner_ids・reviewer_ids には Raimo のユーザーID かログインメールを入れる（管理者かどうかでは判定しない）。
-- 読み書きは service_role（raimo-auth 関数と Miss Lemon の反映作業）だけ。
create table if not exists public.qa_feature_flags (
  feature text primary key check (feature ~ '^[a-z0-9_]{1,40}$'),
  stage text not null default 'off' check (stage in ('off','owner','reviewers','all')),
  owner_ids text[] not null default '{}',
  reviewer_ids text[] not null default '{}',
  note text not null default '',
  updated_at timestamptz not null default now()
);
alter table public.qa_feature_flags enable row level security;
revoke all on public.qa_feature_flags from public, anon, authenticated;
grant select, insert, update on public.qa_feature_flags to service_role;

-- 改善提案(1)〜(3)。最初は全部オフ。
insert into public.qa_feature_flags (feature, note) values
  ('cost_saving',   '(1) AI使用量の削減（意味検索ベース・モデル使い分け・回答の再利用）'),
  ('answer_feedback','(2) 回答へのいいね／悪いね／超いいね＋意見'),
  ('auto_approval', '(3) 名簿一致の自動承認（まず候補表示）')
on conflict (feature) do nothing;
