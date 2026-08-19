-- MQ会計評価: 対象年度の source=import を原子的に置換。manual は保護。
-- jarvis-dashboard のみ。

create or replace function public.kurashift_mq_replace_year_import(
  p_year integer,
  p_rows jsonb,
  p_force boolean default false
)
returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
  rec record;
  v_upserted integer := 0;
  v_deleted integer := 0;
  v_skipped integer := 0;
  v_is_manual boolean;
  v_month date;
begin
  if p_year is null or p_year < 2000 or p_year > 2100 then
    raise exception 'invalid p_year';
  end if;
  if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
    raise exception 'p_rows must be a JSON array';
  end if;

  create temporary table if not exists _mq_import_keep (
    business_line text not null,
    entity text not null,
    period_month date not null,
    primary key (business_line, entity, period_month)
  ) on commit drop;
  truncate table _mq_import_keep;

  for rec in
    select
      e->>'business_line' as business_line,
      e->>'entity' as entity,
      e->>'period_month' as period_month_raw,
      nullif(e->>'q', '')::numeric as q,
      coalesce(nullif(e->>'pq', '')::numeric, 0) as pq,
      coalesce(nullif(e->>'vq', '')::numeric, 0) as vq,
      coalesce(nullif(e->>'f', '')::numeric, 0) as f,
      coalesce(nullif(e->>'f_annual', '')::numeric, 0) as f_annual,
      nullif(e->>'cash_in', '')::numeric as cash_in,
      nullif(e->>'cash_out', '')::numeric as cash_out,
      e->>'note' as note
    from jsonb_array_elements(p_rows) e
  loop
    if rec.business_line not in ('realestate', 'ai') then
      continue;
    end if;
    if rec.entity not in ('personal', 'corporate') then
      continue;
    end if;
    if rec.period_month_raw is null or length(rec.period_month_raw) < 7 then
      continue;
    end if;
    v_month := rec.period_month_raw::date;
    if extract(year from v_month)::integer <> p_year then
      continue;
    end if;

    select exists (
      select 1
      from public.kurashift_mq_period_facts f
      where f.business_line = rec.business_line
        and f.entity = rec.entity
        and f.period_month = v_month
        and f.scenario_kind = 'actual'
        and f.plan_variant_id = ''
        and f.source = 'manual'
    ) into v_is_manual;

    if v_is_manual and not coalesce(p_force, false) then
      v_skipped := v_skipped + 1;
      continue;
    end if;

    insert into public.kurashift_mq_period_facts (
      business_line,
      entity,
      period_month,
      scenario_kind,
      plan_variant_id,
      q,
      pq,
      vq,
      f,
      f_annual,
      cash_in,
      cash_out,
      cash_end,
      note,
      source,
      updated_at
    ) values (
      rec.business_line,
      rec.entity,
      v_month,
      'actual',
      '',
      rec.q,
      rec.pq,
      rec.vq,
      rec.f,
      rec.f_annual,
      rec.cash_in,
      rec.cash_out,
      null,
      coalesce(rec.note, format('Zaim取込 %s（万円・Qは未設定・手入力可）', p_year)),
      'import',
      now()
    )
    on conflict (business_line, entity, period_month, scenario_kind, plan_variant_id)
    do update set
      q = excluded.q,
      pq = excluded.pq,
      vq = excluded.vq,
      f = excluded.f,
      f_annual = excluded.f_annual,
      cash_in = excluded.cash_in,
      cash_out = excluded.cash_out,
      note = excluded.note,
      source = 'import',
      updated_at = now();

    insert into _mq_import_keep (business_line, entity, period_month)
    values (rec.business_line, rec.entity, v_month)
    on conflict do nothing;
    v_upserted := v_upserted + 1;
  end loop;

  delete from public.kurashift_mq_period_facts f
  where f.scenario_kind = 'actual'
    and f.source = 'import'
    and f.period_month >= make_date(p_year, 1, 1)
    and f.period_month < make_date(p_year + 1, 1, 1)
    and not exists (
      select 1
      from _mq_import_keep k
      where k.business_line = f.business_line
        and k.entity = f.entity
        and k.period_month = f.period_month
    );
  get diagnostics v_deleted = row_count;

  return jsonb_build_object(
    'upserted', v_upserted,
    'deleted_stale', v_deleted,
    'skipped_manual', v_skipped
  );
end;
$$;

revoke all on function public.kurashift_mq_replace_year_import(integer, jsonb, boolean) from public;
grant execute on function public.kurashift_mq_replace_year_import(integer, jsonb, boolean)
  to authenticated, service_role;

comment on function public.kurashift_mq_replace_year_import(integer, jsonb, boolean) is
  '対象年度の MQ source=import を原子置換。p_force=false なら source=manual を保護。';
