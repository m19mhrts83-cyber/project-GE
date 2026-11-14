-- 618 latest normal proof. Apply only after owner approval; does not enroll any owner automatically.
begin;
create table public.asset_evidence_owners (
  user_id uuid primary key references auth.users(id),
  created_at timestamptz not null default now()
);
alter table public.asset_evidence_owners enable row level security;
revoke all on public.asset_evidence_owners from anon, authenticated;
grant select on public.asset_evidence_owners to authenticated;
grant all on public.asset_evidence_owners to service_role;
create policy asset_evidence_owner_self on public.asset_evidence_owners
  for select to authenticated using (user_id = auth.uid());

create table public.asset_evidence_latest (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.asset_evidence_owners(user_id),
  account_scope text not null check (account_scope in ('portfolio','liquidity')),
  account_id text not null check (account_id ~ '^[a-zA-Z0-9_-]{1,100}$'),
  contract_key text not null check (contract_key ~ '^[a-zA-Z0-9_-]{1,100}$'),
  view_key text not null check (view_key ~ '^[a-zA-Z0-9_-]{1,100}$'),
  storage_path text,
  sha256 text check (sha256 ~ '^[0-9a-f]{64}$'),
  captured_at timestamptz,
  source_as_of date,
  capture_run_id uuid,
  run_id uuid,
  active_slot text check (active_slot in ('a','b')),
  verified_by text check (verified_by in ('owner','jarvis','codex','misslemon')),
  last_attempt_id uuid,
  last_attempt_at timestamptz,
  last_attempt_status text not null default 'none' check (last_attempt_status in ('none','pending','ok','failed')),
  last_attempt_code text,
  unique(owner_id, account_scope, account_id, contract_key, view_key),
  check ((storage_path is null and sha256 is null and captured_at is null and active_slot is null)
      or (storage_path is not null and sha256 is not null and captured_at is not null and active_slot is not null and source_as_of is not null and run_id is not null and capture_run_id is not null and verified_by is not null))
);
alter table public.asset_evidence_latest enable row level security;
revoke all on public.asset_evidence_latest from anon, authenticated;
grant select on public.asset_evidence_latest to authenticated;
grant all on public.asset_evidence_latest to service_role;
create policy asset_evidence_latest_owner on public.asset_evidence_latest for select to authenticated
  using (owner_id = auth.uid() and exists (select 1 from public.asset_evidence_owners where user_id = auth.uid()));

-- Exactly two bounded slots, one visible pointer. Inactive uploads never replace the active good proof.
insert into storage.buckets(id, name, public, file_size_limit, allowed_mime_types)
 values ('asset-evidence','asset-evidence',false,10485760,array['image/png']) on conflict (id) do nothing;
do $$ begin
 if exists(select 1 from storage.buckets where id='asset-evidence' and public) then
  raise exception 'asset-evidence must be private';
 end if;
end $$;
create policy asset_evidence_select on storage.objects for select to authenticated using (
 bucket_id='asset-evidence' and exists (select 1 from public.asset_evidence_latest e
 where e.owner_id=auth.uid() and e.storage_path=name));
-- Restrictive boundary also covers preexisting broad storage policies.
create policy asset_evidence_read_boundary on storage.objects as restrictive for select to anon,authenticated using (
 bucket_id <> 'asset-evidence' or exists (select 1 from public.asset_evidence_latest e
 where e.owner_id=auth.uid() and e.storage_path=name));
create policy asset_evidence_insert_boundary on storage.objects as restrictive for insert to anon,authenticated
 with check (bucket_id <> 'asset-evidence');
create policy asset_evidence_update_boundary on storage.objects as restrictive for update to anon,authenticated
 using (bucket_id <> 'asset-evidence') with check (bucket_id <> 'asset-evidence');
create policy asset_evidence_delete_boundary on storage.objects as restrictive for delete to anon,authenticated
 using (bucket_id <> 'asset-evidence');

create function public.asset_evidence_begin(p_owner uuid,p_scope text,p_account text,p_contract text,p_view text,p_attempt uuid)
 returns public.asset_evidence_latest language plpgsql set search_path=public as $$
declare r public.asset_evidence_latest;
begin
 if (p_scope='portfolio' and not exists(select 1 from public.portfolio_accounts where id=p_account and active))
 or (p_scope='liquidity' and not exists(select 1 from public.liquidity_accounts where id=p_account and active)) then
  raise exception 'unknown active account';
 end if;
 insert into public.asset_evidence_latest(owner_id,account_scope,account_id,contract_key,view_key)
 values(p_owner,p_scope,p_account,p_contract,p_view) on conflict do nothing;
 select * into strict r from public.asset_evidence_latest where owner_id=p_owner and account_scope=p_scope
 and account_id=p_account and contract_key=p_contract and view_key=p_view for update;
 if r.last_attempt_status='pending' then raise exception 'evidence update pending; review before recovery'; end if;
 update public.asset_evidence_latest set last_attempt_id=p_attempt,last_attempt_at=now(),
 last_attempt_status='pending',last_attempt_code=null where id=r.id returning * into r;
 return r;
end $$;
create function public.asset_evidence_commit(p_id uuid,p_attempt uuid,p_sha text,p_captured timestamptz,
 p_asof date,p_capture_run uuid,p_run uuid,p_reviewer text)
 returns public.asset_evidence_latest language plpgsql set search_path=public as $$
declare r public.asset_evidence_latest; slot text;
begin
 select * into strict r from public.asset_evidence_latest where id=p_id for update;
 if r.last_attempt_id is distinct from p_attempt or r.last_attempt_status <> 'pending' then raise exception 'attempt mismatch'; end if;
 if p_captured > now()+interval '5 seconds' or p_asof > (p_captured at time zone 'Asia/Tokyo')::date then raise exception 'future proof'; end if;
 if r.captured_at is not null and (p_captured <= r.captured_at or p_asof < r.source_as_of) then raise exception 'older proof'; end if;
 slot := case when r.active_slot='a' then 'b' else 'a' end;
 update public.asset_evidence_latest set storage_path='618/latest/'||owner_id||'/'||account_scope||'/'||account_id||'/'||contract_key||'/'||view_key||'.'||slot||'.png',
 active_slot=slot,sha256=p_sha,captured_at=p_captured,source_as_of=p_asof,capture_run_id=p_capture_run,
 run_id=p_run,verified_by=p_reviewer,last_attempt_status='ok',last_attempt_code=null where id=r.id returning * into r;
 return r;
end $$;
create function public.asset_evidence_fail(p_id uuid,p_attempt uuid)
 returns void language sql set search_path=public as $$
 update public.asset_evidence_latest set last_attempt_status='failed',last_attempt_code='update_failed'
 where id=p_id and last_attempt_id=p_attempt and last_attempt_status='pending';
$$;
-- Explicit recovery only after a human/operator confirms that the pending publisher has stopped.
create function public.asset_evidence_recover(p_id uuid,p_attempt uuid)
 returns void language sql set search_path=public as $$
 update public.asset_evidence_latest set last_attempt_status='failed',last_attempt_code='operator_recovered'
 where id=p_id and last_attempt_id=p_attempt and last_attempt_status='pending';
$$;
revoke all on function public.asset_evidence_begin(uuid,text,text,text,text,uuid) from public,anon,authenticated;
revoke all on function public.asset_evidence_commit(uuid,uuid,text,timestamptz,date,uuid,uuid,text) from public,anon,authenticated;
revoke all on function public.asset_evidence_fail(uuid,uuid) from public,anon,authenticated;
revoke all on function public.asset_evidence_recover(uuid,uuid) from public,anon,authenticated;
grant execute on function public.asset_evidence_begin(uuid,text,text,text,text,uuid) to service_role;
grant execute on function public.asset_evidence_commit(uuid,uuid,text,timestamptz,date,uuid,uuid,text) to service_role;
grant execute on function public.asset_evidence_fail(uuid,uuid) to service_role;
grant execute on function public.asset_evidence_recover(uuid,uuid) to service_role;

create table public.asset_618_display_checks (
 owner_id uuid not null references public.asset_evidence_owners(user_id),
 run_id uuid not null,
 numeric_digest text not null check (numeric_digest ~ '^[0-9a-f]{64}$'),
 matched_count integer not null check (matched_count > 0),
 unresolved_count integer not null check (unresolved_count >= 0),
 checked_at timestamptz not null default now(),
 primary key (owner_id,run_id)
);
alter table public.asset_618_display_checks enable row level security;
revoke all on public.asset_618_display_checks from anon,authenticated;
grant select,insert,update on public.asset_618_display_checks to authenticated;
grant all on public.asset_618_display_checks to service_role;
create policy asset_618_display_owner on public.asset_618_display_checks for all to authenticated
 using(owner_id=auth.uid() and exists(select 1 from public.asset_evidence_owners where user_id=auth.uid()))
 with check(owner_id=auth.uid() and exists(select 1 from public.asset_evidence_owners where user_id=auth.uid()));
commit;
