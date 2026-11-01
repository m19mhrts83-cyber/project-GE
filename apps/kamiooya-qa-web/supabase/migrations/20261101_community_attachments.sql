-- Internal attachment ingestion. Member-facing access is added separately.
begin;
create table if not exists public.community_attachments (
  id text primary key check (id ~ '^[0-9a-f]{64}$'),
  comment_id text not null references public.comments(comment_id) on delete restrict,
  bucket text not null check (bucket = 'community-attachments'),
  storage_path text not null,
  source_url text not null,
  original_name text not null,
  content_type text not null,
  byte_size bigint not null check (byte_size > 0 and byte_size <= 20971520),
  sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (comment_id, source_url)
);
create index if not exists community_attachments_comment_idx on public.community_attachments(comment_id);
alter table public.community_attachments enable row level security;
revoke all on public.community_attachments from anon, authenticated;
grant all on public.community_attachments to service_role;
notify pgrst, 'reload schema';
commit;
