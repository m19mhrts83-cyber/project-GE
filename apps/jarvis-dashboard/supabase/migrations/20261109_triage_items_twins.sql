-- 判断デスクに同じメールが2枚出る問題（2026-11-09）
-- Mac の夜間仕分け（id = 12桁ハッシュ）と GHA の仕分け（id = gha- / gha-p- / gha-cw- + 同じハッシュ）が
-- 同じメールを別々の id で入れていた。片方を判断しても、もう片方が pending のまま残る。
--
-- 1) 新しく入る行は、同じハッシュの行（双子）がすでにあれば入れない（先に入った方を正にする）
-- 2) 片方が pending から判断済みになったら、pending の双子にも同じ状態を写す
-- 3) pending のまま上書きされる行（仕分けの再送）は、双子が判断済みならその状態に合わせる
--    （判断済み → pending に戻す操作はそのまま通す）
-- 4) 双子へ写しただけの変化は判断ログ（owner_decisions）に二重に入れない
--    （triage_items_log_owner_decision の先頭に payload.twin_synced_from の見張りを足す）
-- 5) いま残っている双子（2026-11-09 時点 67 組）を片付ける
--    - 片方が判断済み → pending の方を同じ状態に（判断ログは増えない）
--    - 両方 pending → 先に入った方を残し、後の方は skipped＋payload.twin_hidden=true で隠す
--      （残した方を判断したら、隠した方にも同じ状態が写る）
-- 戻すとき:
--   drop trigger triage_items_twins_before on public.triage_items;
--   drop trigger triage_items_twins_after on public.triage_items;
--   drop function public.triage_items_twins_before_fn(); drop function public.triage_items_twins_after_fn();

create or replace function public.triage_twin_key(i text) returns text
language sql immutable as $$ select regexp_replace(i, '^gha-(cw-|p-)?', '') $$;

create index if not exists triage_items_twin_key_idx on public.triage_items (public.triage_twin_key(id));

create or replace function public.triage_items_twins_before_fn() returns trigger
language plpgsql as $$
declare
  twin_status text;
begin
  if tg_op = 'INSERT' then
    if not exists (select 1 from public.triage_items t where t.id = new.id)
       and exists (select 1 from public.triage_items t
                   where public.triage_twin_key(t.id) = public.triage_twin_key(new.id) and t.id <> new.id) then
      return null;  -- 双子がもういる
    end if;
  end if;
  if tg_op = 'UPDATE' then
    -- 仕分けの再送で payload が丸ごと置き換わっても、双子の印は残す
    new.payload := coalesce(new.payload, '{}'::jsonb)
      || jsonb_strip_nulls(jsonb_build_object(
           'twin_hidden', case when new.payload ? 'twin_hidden' then null else old.payload -> 'twin_hidden' end,
           'twin_synced_from', case when new.payload ? 'twin_synced_from' then null else old.payload -> 'twin_synced_from' end));
  end if;
  if new.status = 'pending' and (tg_op = 'INSERT' or old.status = 'pending') then
    select t.status into twin_status from public.triage_items t
     where public.triage_twin_key(t.id) = public.triage_twin_key(new.id) and t.id <> new.id
       and t.status not in ('pending', 'snoozed')
     order by t.updated_at desc nulls last limit 1;
    if twin_status is not null then
      new.status := twin_status;
      new.payload := coalesce(new.payload, '{}'::jsonb) || jsonb_build_object('twin_synced_from', 'twin');
    end if;
  end if;
  return new;
end $$;

create or replace function public.triage_items_twins_after_fn() returns trigger
language plpgsql as $$
begin
  if old.status in ('pending', 'snoozed') and new.status not in ('pending', 'snoozed')
     and coalesce(new.payload ->> 'twin_hidden', '') <> 'true' then  -- 隠しただけの変化は写さない
    update public.triage_items t
       set status = new.status,
           payload = coalesce(t.payload, '{}'::jsonb) || jsonb_build_object('twin_synced_from', new.id),
           updated_at = now()
     where public.triage_twin_key(t.id) = public.triage_twin_key(new.id)
       and t.id <> new.id
       and (t.status in ('pending', 'snoozed') or coalesce(t.payload ->> 'twin_hidden', '') = 'true');
  end if;
  return null;
end $$;

drop trigger if exists triage_items_twins_before on public.triage_items;
create trigger triage_items_twins_before before insert or update on public.triage_items
  for each row execute function public.triage_items_twins_before_fn();

drop trigger if exists triage_items_twins_after on public.triage_items;
create trigger triage_items_twins_after after update of status on public.triage_items
  for each row execute function public.triage_items_twins_after_fn();

-- 4) 判断ログの関数に見張りを足す（本体は 20261108_owner_decisions_trigger_v1.sql のまま）
do $do$
declare d text;
begin
  d := pg_get_functiondef('public.triage_items_log_owner_decision'::regproc);
  if position('twin_synced_from' in d) = 0 then
    d := replace(d,
      E'begin\n  if coalesce(old.status, \'pending\') <> \'pending\'',
      E'begin\n  -- 双子（同じメールの別 id）へ写しただけの変化は判断ログに入れない（20261109_triage_items_twins）\n'
      || E'  if (new.payload ->> \'twin_synced_from\') is distinct from (old.payload ->> \'twin_synced_from\') then\n'
      || E'    return new;\n  end if;\n  if coalesce(old.status, \'pending\') <> \'pending\'');
    if position('twin_synced_from' in d) = 0 then
      raise exception 'triage_items_log_owner_decision の形が想定と違うため見張りを足せませんでした';
    end if;
    execute d;
  end if;
end
$do$;

-- 5) いま残っている双子を片付ける（何度流しても同じ結果）
update public.triage_items t
   set updated_at = now()   -- before トリガーが双子の判断済み状態に合わせる
 where t.status = 'pending'
   and exists (select 1 from public.triage_items u
                where public.triage_twin_key(u.id) = public.triage_twin_key(t.id) and u.id <> t.id
                  and u.status not in ('pending', 'snoozed'));

with g as (
  select id, row_number() over (partition by public.triage_twin_key(id) order by updated_at asc nulls last, id) rn
    from public.triage_items
   where public.triage_twin_key(id) in (
     select public.triage_twin_key(id) from public.triage_items group by 1 having count(*) > 1)
     and status = 'pending'
)
update public.triage_items t
   set status = 'skipped',
       payload = coalesce(t.payload, '{}'::jsonb)
                 || jsonb_build_object('twin_hidden', true, 'twin_synced_from', 'twin', 'twin_hidden_at', now())
  from g
 where g.id = t.id and g.rn > 1;
