-- Shared, service-only sessions. No bearer tokens or passwords are stored here.
create table if not exists public.raimo_auth_sessions (
 token_hash text primary key check (token_hash ~ '^[0-9a-f]{64}$'),
 user_id text not null,
 auth_version text not null,
 expires_at timestamptz not null
);
alter table public.raimo_auth_sessions enable row level security;
revoke all on public.raimo_auth_sessions from public, anon, authenticated;
grant select, insert, update, delete on public.raimo_auth_sessions to service_role;
create index if not exists raimo_auth_sessions_expiry on public.raimo_auth_sessions(expires_at);
create table if not exists public.raimo_auth_limits (
 key_hash text primary key,
 window_start timestamptz not null,
 attempts integer not null check (attempts > 0)
);
alter table public.raimo_auth_limits enable row level security;
revoke all on public.raimo_auth_limits from public, anon, authenticated;
revoke all on public.raimo_auth_limits from service_role;
create or replace function public.raimo_auth_take_limit(key_hash text, max_attempts integer, window_seconds integer)
returns boolean language plpgsql security definer set search_path = public, pg_temp as $$
declare hits integer;
begin
 if key_hash !~ '^[0-9a-f]{64}$' or max_attempts not between 1 and 100 or window_seconds not between 60 and 3600 then
  raise exception 'invalid_limit';
 end if;
 insert into public.raimo_auth_limits as limits values(key_hash, now(), 1)
 on conflict on constraint raimo_auth_limits_pkey do update
 set window_start = case when limits.window_start < now()-make_interval(secs=>window_seconds) then now() else limits.window_start end,
 attempts = case when limits.window_start < now()-make_interval(secs=>window_seconds) then 1 else least(limits.attempts+1,101) end
 returning attempts into hits;
 -- Bounded retention for per-IP and per-account counters, including nonexistent accounts.
 delete from public.raimo_auth_limits where window_start < now()-interval '2 hours';
 delete from public.raimo_auth_sessions where expires_at < now()-interval '1 day';
 return hits <= max_attempts;
end $$;
revoke all on function public.raimo_auth_take_limit(text,integer,integer) from public, anon, authenticated;
grant execute on function public.raimo_auth_take_limit(text,integer,integer) to service_role;
