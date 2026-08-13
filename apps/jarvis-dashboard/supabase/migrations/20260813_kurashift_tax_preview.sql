-- 確定申告証憑の画面プレビュー用（Storage + storage_path）
alter table public.kurashift_tax_evidence add column if not exists storage_path text;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'kurashift-tax',
  'kurashift-tax',
  false,
  52428800,
  null
)
on conflict (id) do nothing;

drop policy if exists kurashift_tax_objects_select on storage.objects;
create policy kurashift_tax_objects_select
on storage.objects for select
to authenticated
using (bucket_id = 'kurashift-tax');
