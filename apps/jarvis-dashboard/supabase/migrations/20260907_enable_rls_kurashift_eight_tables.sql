-- ==============================================================================
-- KURASHIFT RLS OFF 8表の行レベルセキュリティ有効化
-- 日付: 2026-09-07
-- 設計方針: 【案A】authenticated（ログイン済みユーザー）に全権限を付与し、
--          anon（未認証アクセス）を完全に遮断する。
--          service_role（Jarvisバッチ）はRLSバイパスのため影響なし。
-- ==============================================================================

-- 1. kurashift_re_deals
alter table public.kurashift_re_deals enable row level security;
drop policy if exists kurashift_re_deals_auth_all on public.kurashift_re_deals;
create policy kurashift_re_deals_auth_all on public.kurashift_re_deals
  for all to authenticated using (true) with check (true);

-- 2. kurashift_buy_plan_constraints
alter table public.kurashift_buy_plan_constraints enable row level security;
drop policy if exists kurashift_buy_plan_constraints_auth_all on public.kurashift_buy_plan_constraints;
create policy kurashift_buy_plan_constraints_auth_all on public.kurashift_buy_plan_constraints
  for all to authenticated using (true) with check (true);

-- 3. kurashift_buy_plan_criteria
alter table public.kurashift_buy_plan_criteria enable row level security;
drop policy if exists kurashift_buy_plan_criteria_auth_all on public.kurashift_buy_plan_criteria;
create policy kurashift_buy_plan_criteria_auth_all on public.kurashift_buy_plan_criteria
  for all to authenticated using (true) with check (true);

-- 4. kurashift_buy_plan_events
alter table public.kurashift_buy_plan_events enable row level security;
drop policy if exists kurashift_buy_plan_events_auth_all on public.kurashift_buy_plan_events;
create policy kurashift_buy_plan_events_auth_all on public.kurashift_buy_plan_events
  for all to authenticated using (true) with check (true);

-- 5. kurashift_buy_plan_notes
alter table public.kurashift_buy_plan_notes enable row level security;
drop policy if exists kurashift_buy_plan_notes_auth_all on public.kurashift_buy_plan_notes;
create policy kurashift_buy_plan_notes_auth_all on public.kurashift_buy_plan_notes
  for all to authenticated using (true) with check (true);

-- 6. kurashift_buy_plan_versions
alter table public.kurashift_buy_plan_versions enable row level security;
drop policy if exists kurashift_buy_plan_versions_auth_all on public.kurashift_buy_plan_versions;
create policy kurashift_buy_plan_versions_auth_all on public.kurashift_buy_plan_versions
  for all to authenticated using (true) with check (true);

-- 7. kurashift_loan_tracker_loans
alter table public.kurashift_loan_tracker_loans enable row level security;
drop policy if exists kurashift_loan_tracker_loans_auth_all on public.kurashift_loan_tracker_loans;
create policy kurashift_loan_tracker_loans_auth_all on public.kurashift_loan_tracker_loans
  for all to authenticated using (true) with check (true);

-- 8. kurashift_ops_consult_events
alter table public.kurashift_ops_consult_events enable row level security;
drop policy if exists kurashift_ops_consult_events_auth_all on public.kurashift_ops_consult_events;
create policy kurashift_ops_consult_events_auth_all on public.kurashift_ops_consult_events
  for all to authenticated using (true) with check (true);
