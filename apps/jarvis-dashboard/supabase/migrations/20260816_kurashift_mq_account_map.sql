-- MQ会計評価 Phase C: Zaim科目→MQ要素マッピング

create table if not exists public.kurashift_mq_account_map (
  id uuid primary key default gen_random_uuid(),
  business_line text not null
    check (business_line in ('realestate', 'ai')),
  category_match text not null default '',
  subcategory_match text not null default '',
  -- 空文字はワイルドカード（すべて一致）
  entity_match text not null default ''
    check (entity_match in ('', 'personal', 'corporate')),
  mq_element text not null
    check (mq_element in (
      'pq', 'vq', 'f', 'f_annual', 'cash_out', 'exclude'
    )),
  combine_treatment text not null default 'include'
    check (combine_treatment in ('include', 'exclude_on_combined')),
  priority int not null default 100,
  approved boolean not null default false,
  note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists kurashift_mq_account_map_line_idx
  on public.kurashift_mq_account_map (business_line, approved);

alter table public.kurashift_mq_account_map enable row level security;

drop policy if exists kurashift_mq_account_map_auth_all
  on public.kurashift_mq_account_map;
create policy kurashift_mq_account_map_auth_all
  on public.kurashift_mq_account_map
  for all to authenticated
  using (true)
  with check (true);

-- 既定マップ（承認済み）。category/sub は部分一致（includes）
insert into public.kurashift_mq_account_map
  (business_line, category_match, subcategory_match, entity_match, mq_element, combine_treatment, priority, approved, note)
select * from (values
  ('realestate', '19.1', '家賃', '', 'pq', 'include', 10, true, '家賃収入'),
  ('realestate', '19.1', '', '', 'pq', 'include', 20, true, '19.1系家賃'),
  ('realestate', '賃貸', '外注管理', '', 'vq', 'include', 30, true, '管理手数料％'),
  ('realestate', '賃貸', '管理費', '', 'vq', 'include', 31, true, '管理費'),
  ('realestate', '賃貸', '租税公課', '', 'f_annual', 'include', 40, true, '固都税・年額'),
  ('realestate', '賃貸', '固定資産', '', 'f_annual', 'include', 41, true, '固定資産税'),
  ('realestate', '賃貸', '修繕', '', 'f', 'include', 50, true, '修繕'),
  ('realestate', '賃貸', '火災保険', '', 'f_annual', 'include', 51, true, '保険年払'),
  ('realestate', '賃貸', '税理士', '', 'f', 'include', 52, true, '税理士'),
  ('realestate', '賃貸', '法人税', '', 'f', 'include', 53, true, '法人税'),
  ('realestate', '賃貸', 'ローン', '', 'cash_out', 'include', 5, true, '元利一体→Gに入れない'),
  ('realestate', '賃貸', '経費', '', 'f', 'include', 80, true, 'その他経費'),
  ('realestate', '賃貸経営', '', '', 'f', 'include', 90, true, '賃貸経営フォールバック'),
  ('ai', 'AIリスキリング', '加盟金', '', 'f', 'include', 10, true, '加盟金'),
  ('ai', 'AIリスキリング', '', '', 'f', 'include', 20, true, 'AI経費'),
  ('ai', '21F', '', '', 'f', 'include', 30, true, '21F系')
) as v(business_line, category_match, subcategory_match, entity_match, mq_element, combine_treatment, priority, approved, note)
where not exists (select 1 from public.kurashift_mq_account_map limit 1);

comment on table public.kurashift_mq_account_map is
  'Zaim category/subcategory → MQ要素。approved=true のみ自動取込に使う。';
