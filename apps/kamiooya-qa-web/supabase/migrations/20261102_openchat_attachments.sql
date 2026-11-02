-- Private backup only: member viewing is a separate release.
insert into storage.buckets (id,name,public,file_size_limit)
values ('openchat-attachments','openchat-attachments',false,524288000)
on conflict (id) do nothing;

-- Existing permissive policies for other buckets must not expose this archive.
create policy openchat_archive_service_only on storage.objects
as restrictive for all to anon,authenticated
using (bucket_id <> 'openchat-attachments')
with check (bucket_id <> 'openchat-attachments');

create table if not exists public.openchat_attachments (
 id text primary key check (id ~ '^[0-9a-f]{64}$'),
 room_id text not null, message_id text not null, thread_id text not null default '',
 kind text not null check (kind in ('image','video','audio','file')),
 original_name text not null, content_type text not null,
 byte_size bigint not null check (byte_size > 0 and byte_size <= 524288000),
 sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
 bucket text not null default 'openchat-attachments' check (bucket='openchat-attachments'),
 storage_path text not null check (storage_path ~ '^objects/[0-9a-f]{64}$'),
 saved_at timestamptz not null default now(), unique(room_id,message_id)
);
alter table public.openchat_attachments enable row level security;
revoke all on public.openchat_attachments from anon,authenticated;
grant select,insert,update on public.openchat_attachments to service_role;

-- Includes all buckets in this project, not just the new attachment bucket.
create or replace function public.openchat_backup_storage_bytes()
returns bigint language sql stable security definer set search_path = '' as $$
 select case when count(*) filter (where metadata->>'size' is null or
   not (metadata->>'size' ~ '^[0-9]+$'))>0 then null
   else coalesce(sum((metadata->>'size')::bigint),0)::bigint end from storage.objects;
$$;
revoke all on function public.openchat_backup_storage_bytes() from public,anon,authenticated;
grant execute on function public.openchat_backup_storage_bytes() to service_role;
