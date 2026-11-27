-- 見る専用（viewer）ロール。2026-11-27
-- app_metadata.role = 'viewer' の JWT は、public の全表と storage.objects への insert/update/delete を拒否する。
-- 既存の「authenticated は全部可」ポリシーに AND で効く restrictive ポリシー。select は変えない。
-- service_role はバイパスなので既存の収集・書き込みジョブに影響しない。
-- 新しい表を足したら、末尾の関数 public.apply_viewer_readonly(regclass) を同じ migration で呼ぶこと。

create or replace function public.is_viewer() returns boolean
language sql stable as $$
  select coalesce(auth.jwt() -> 'app_metadata' ->> 'role', '') = 'viewer'
$$;

create or replace function public.apply_viewer_readonly(tbl regclass) returns void
language plpgsql as $$
declare cmd text;
begin
  foreach cmd in array array['insert', 'update', 'delete'] loop
    execute format('drop policy if exists viewer_no_%s on %s', cmd, tbl);
    if cmd = 'insert' then
      execute format('create policy viewer_no_insert on %s as restrictive for insert to authenticated with check (not public.is_viewer())', tbl);
    else
      execute format('create policy viewer_no_%s on %s as restrictive for %s to authenticated using (not public.is_viewer())', cmd, tbl, cmd);
    end if;
  end loop;
end $$;

do $$
declare r record;
begin
  for r in
    select c.oid::regclass as tbl
    from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind in ('r', 'p') and c.relrowsecurity
  loop
    perform public.apply_viewer_readonly(r.tbl);
  end loop;
end $$;

-- RLS を有効にしていない public 表は authenticated に権限があれば書ける。viewer 用に権限を外せるよう検出だけ残す（notice）
do $$
declare r record;
begin
  for r in
    select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind in ('r', 'p') and not c.relrowsecurity
  loop
    raise notice 'RLS 無効の表（viewer 制限の対象外。要確認）: %', r.relname;
  end loop;
end $$;

-- Storage（storage.objects の所有者権限が無い環境では失敗するので、その時は SQL Editor で実行）
select public.apply_viewer_readonly('storage.objects'::regclass);
