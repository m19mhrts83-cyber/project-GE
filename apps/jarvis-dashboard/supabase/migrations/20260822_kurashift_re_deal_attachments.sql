-- Phase PDF-0: 問合せ返信 PDF 等の添付メタ（実体は Mac .jarvis_state）

create table if not exists public.kurashift_re_deal_attachments (
  id uuid primary key default gen_random_uuid(),
  deal_id uuid not null references public.kurashift_re_deals(id) on delete cascade,
  gmail_id text,
  message_id uuid references public.kurashift_re_deal_messages(id) on delete set null,
  filename text not null,
  mime_type text not null default 'application/pdf',
  size_bytes bigint,
  storage_path text not null,
  fetched_at timestamptz not null default now(),
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create unique index if not exists kurashift_re_deal_attachments_gmail_filename_uidx
  on public.kurashift_re_deal_attachments (deal_id, gmail_id, filename)
  where gmail_id is not null;

create index if not exists kurashift_re_deal_attachments_deal_idx
  on public.kurashift_re_deal_attachments (deal_id, fetched_at desc);

alter table public.kurashift_re_deal_attachments enable row level security;

drop policy if exists kurashift_re_deal_attachments_auth_all on public.kurashift_re_deal_attachments;
create policy kurashift_re_deal_attachments_auth_all
  on public.kurashift_re_deal_attachments
  for all to authenticated
  using (true)
  with check (true);
