-- Supabase SQL Editor に貼り付けて実行してください（無料枠OK）
-- Raimo版のテーブル構成をNext.js側で再現するための最低限スキーマ

create table if not exists public.users (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  password_hash text not null,
  role text not null default 'user' check (role in ('user','admin')),
  status text not null default 'pending' check (status in ('pending','approved')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.comments (
  id uuid primary key default gen_random_uuid(),
  source_type text,
  comment_id text,
  posted_at timestamptz,
  author_name text,
  author_email text,
  content text not null,
  parent_comment_id text,
  ip_address text,
  user_agent text,
  created_at timestamptz not null default now()
);

create index if not exists comments_posted_at_idx on public.comments (posted_at desc nulls last);
create index if not exists comments_source_type_idx on public.comments (source_type);
create index if not exists comments_comment_id_idx on public.comments (comment_id);

create table if not exists public.suggested_questions (
  id uuid primary key default gen_random_uuid(),
  question_text text not null unique,
  frequency integer not null default 1,
  created_at timestamptz not null default now()
);

create index if not exists suggested_questions_frequency_idx on public.suggested_questions (frequency desc);

create table if not exists public.chat_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.users(id) on delete cascade,
  title text,
  created_at timestamptz not null default now()
);

create index if not exists chat_sessions_user_id_idx on public.chat_sessions (user_id, created_at desc);

create table if not exists public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.chat_sessions(id) on delete cascade,
  role text not null check (role in ('user','assistant')),
  content text not null,
  created_at timestamptz not null default now()
);

create index if not exists chat_messages_session_id_idx on public.chat_messages (session_id, created_at asc);

