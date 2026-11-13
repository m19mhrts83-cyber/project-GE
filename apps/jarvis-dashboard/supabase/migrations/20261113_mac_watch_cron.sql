-- Mac 見張りを 5 分ごとに呼ぶ（Supabase pg_cron + pg_net）。GHA の schedule は間引かれるため使わない。
-- 鍵は Vault の 'mac_watch_key'（Vercel の MAC_WATCH_KEY と同じ値）。値はここに書かない。
--   select vault.create_secret('<値>', 'mac_watch_key');  -- 一度だけ、手元で生成した値で
create extension if not exists pg_cron;
create extension if not exists pg_net;

create or replace function public.mac_watch_ping() returns void
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  k text;
begin
  select decrypted_secret into k from vault.decrypted_secrets where name = 'mac_watch_key' limit 1;
  if k is null then
    return;
  end if;
  perform net.http_post(
    url := 'https://jarvis-dashboard-amber.vercel.app/api/mac-watch',
    headers := jsonb_build_object('Authorization', 'Bearer ' || k, 'Content-Type', 'application/json'),
    body := '{}'::jsonb,
    timeout_milliseconds := 15000
  );
end;
$$;

revoke all on function public.mac_watch_ping() from public, anon, authenticated;

select cron.unschedule('mac-watch') where exists (select 1 from cron.job where jobname = 'mac-watch');
select cron.schedule('mac-watch', '*/5 * * * *', $$select public.mac_watch_ping();$$);
