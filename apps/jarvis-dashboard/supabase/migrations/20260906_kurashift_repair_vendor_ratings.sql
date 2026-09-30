-- 修繕業者台帳（kurashift_re_repair_vendors）レーティング評価列の追加
-- jarvis-dashboard (idkdqneutpvkhxhpjtgc)

alter table public.kurashift_re_repair_vendors
  add column if not exists recommend text check (recommend in ('A', 'B', 'C', 'D')),
  add column if not exists cost_rating text check (cost_rating in ('cheap', 'fair', 'expensive', 'unknown')),
  add column if not exists service_rating text check (service_rating in ('good', 'mixed', 'poor', 'unknown')),
  add column if not exists rating_evidence text,
  add column if not exists rating_sources text,
  add column if not exists rated_at date;

create index if not exists kurashift_re_repair_vendors_recommend_idx
  on public.kurashift_re_repair_vendors (recommend, updated_at desc);

-- 既存の sole_proprietor_score から初期 recommend をバックフィル
update public.kurashift_re_repair_vendors
set
  recommend = case
    when sole_proprietor_score = 'high' then 'A'
    when sole_proprietor_score = 'mid' then 'B'
    when sole_proprietor_score = 'low' then 'C'
    else null
  end,
  rated_at = coalesce(discovered_at, current_date)
where recommend is null and sole_proprietor_score is not null;
