-- Preserve the archive identity while recording the higher-resolution source.
begin;
alter table public.community_attachments add column if not exists original_source_url text;
alter table public.community_attachments add column if not exists image_width integer;
alter table public.community_attachments add column if not exists image_height integer;
create or replace function public.prevent_original_image_downgrade()
returns trigger language plpgsql set search_path=public,pg_temp as $$
begin
 if old.original_source_url is not null and (new.original_source_url is null or
    coalesce(new.image_width,0) < old.image_width or coalesce(new.image_height,0) < old.image_height or
    (new.sha256 <> old.sha256 and coalesce(new.image_width,0) <= old.image_width and coalesce(new.image_height,0) <= old.image_height)) then
  raise exception 'original_image_downgrade_blocked';
 end if;
 return new;
end $$;
drop trigger if exists community_original_image_protection on public.community_attachments;
create trigger community_original_image_protection before update on public.community_attachments
for each row execute function public.prevent_original_image_downgrade();
notify pgrst,'reload schema';
commit;
