-- Temporary ChatGPT → Mac handoff. The local Obsidian Vault remains canonical.
create table if not exists public.obsidian_review_inbox (
  review_id uuid primary key,
  review_date date not null,
  raw_log text,
  tactical_review text,
  status text not null default 'pending' check (status in ('pending', 'delivered')),
  created_at timestamptz not null default now(),
  delivered_at timestamptz,
  saved_paths text[]
);

create index if not exists obsidian_review_inbox_pending_created_idx
  on public.obsidian_review_inbox (created_at)
  where status = 'pending';

alter table public.obsidian_review_inbox enable row level security;
revoke all on public.obsidian_review_inbox from anon, authenticated;
grant select, insert, update, delete on public.obsidian_review_inbox to service_role;

comment on table public.obsidian_review_inbox is
  'Temporary handoff only; content is cleared after Mac confirms Vault and OGD save.';
