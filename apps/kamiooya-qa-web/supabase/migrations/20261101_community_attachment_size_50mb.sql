-- Historical PDFs include three originals larger than 20 MiB.
-- Retain private access and the positive-size check; no grants are expanded.
begin;
alter table public.community_attachments drop constraint if exists community_attachments_byte_size_check;
alter table public.community_attachments add constraint community_attachments_byte_size_check
  check (byte_size > 0 and byte_size <= 52428800);
commit;
