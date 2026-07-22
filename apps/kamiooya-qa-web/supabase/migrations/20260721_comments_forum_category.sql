-- Phase 9: comments 分類列（Supabase SQL Editor で実行）
alter table public.comments add column if not exists source_system text;
alter table public.comments add column if not exists source_kind text;
alter table public.comments add column if not exists forum_category text;
alter table public.comments add column if not exists topic_title text;
create index if not exists comments_forum_category_idx on public.comments (forum_category);
