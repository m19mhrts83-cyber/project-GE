-- Supabase Data API: 2026-10-30 以降、public の新規テーブルは明示 GRANT が必須。
-- 既存テーブルの自動 GRANT は維持されるが、db reset / preview / 再適用でも
-- Data API（supabase-js / PostgREST）から見えるよう、存在する表へ明示 GRANT する。
-- 未適用の migration 表はスキップ（to_regclass IS NULL）。
-- 参考: https://github.com/orgs/supabase/discussions/45329
--
-- 方針（jarvis-dashboard）:
--   - authenticated / service_role に DML
--   - anon には付与しない（RLS ポリシーも authenticated 想定）

do $grant$
declare
  t text;
  granted int := 0;
  skipped int := 0;
begin
  foreach t in array array[
    'triage_items',
    'watch_status',
    'cards',
    'card_comments',
    'lane_action_log',
    'metrics',
    'sync_meta',
    'subscription_services',
    'watch_comments',
    'property_units',
    'property_occupancy_events',
    'vital_snore_daily',
    'vital_treatment_events',
    'vital_daily',
    'vital_journal_daily',
    'vital_context_notes',
    'vital_quiet_reviews',
    'glucon_schedule',
    'glucon_journal_days',
    'glucon_report_drafts',
    'glucon_carry_memos',
    'kurashift_jobs',
    'kurashift_consultations',
    'kurashift_themes',
    'kurashift_plan_snapshots',
    'kurashift_tax_cases',
    'kurashift_tax_evidence',
    'liquidity_accounts',
    'liquidity_snapshots',
    'cashflow_week_summaries',
    'securities_holdings',
    'kurashift_money_ops',
    'trade_instruments',
    'trade_prices',
    'trade_signals',
    'trade_orders',
    'trade_positions',
    'trade_daily_pnl',
    'trade_risk_state',
    'trade_params',
    'trade_reviews',
    'trade_research',
    'portfolio_accounts',
    'portfolio_snapshots',
    'portfolio_cashflows',
    'advisor_notes',
    'kurashift_buy_plan_versions',
    'kurashift_buy_plan_events',
    'kurashift_buy_plan_criteria',
    'kurashift_buy_plan_constraints',
    'kurashift_buy_plan_notes',
    'kurashift_re_deals',
    'kurashift_ops_consult_events',
    'kurashift_lifeplan_versions',
    'kurashift_lifeplan_budget_rows',
    'kurashift_lifeplan_sheet_dumps',
    'kurashift_finance_sources',
    'kurashift_finance_transactions',
    'kurashift_finance_category_year',
    'kurashift_loan_tracker_loans',
    'kurashift_tax_year_metrics',
    'kurashift_re_deal_messages',
    'kurashift_auto_pass_learn',
    'kurashift_mq_account_map',
    'kurashift_mq_bs_snapshots',
    'kurashift_mq_period_facts',
    'kurashift_household_bs_snapshots',
    'kurashift_mq_cashflow_settings',
    'kurashift_mq_cashflow_txn_overrides',
    'kurashift_mq_cashflow_classify_rules',
    'kurashift_mq_cashflow_adjustments',
    'kurashift_mq_cashflow_actions',
    'kurashift_mq_cashflow_projections',
    'kurashift_re_deal_attachments',
    'kurashift_re_deal_field_values',
    'kurashift_re_vendors',
    'kurashift_re_deal_events',
    'kurashift_re_mgmt_vendors',
    'kurashift_re_repair_vendors',
    'kurashift_lenders',
    'kurashift_lender_intel',
    'glucon_material_items',
    'kurashift_re_statements',
    'kurashift_re_annual_plans',
    'kurashift_re_actuals',
    'kurashift_re_gl_lines',
    'kurashift_openchat_logs',
    'todoist_webhook_events'
  ]
  loop
    if to_regclass('public.' || t) is null then
      skipped := skipped + 1;
      raise notice 'skip missing table: %', t;
    else
      execute format(
        'grant select, insert, update, delete on table public.%I to authenticated, service_role',
        t
      );
      granted := granted + 1;
    end if;
  end loop;
  -- sequences: 存在する全 public sequence
  execute 'grant usage, select on all sequences in schema public to authenticated, service_role';
  raise notice 'data_api grants: granted=% skipped=%', granted, skipped;
end
$grant$;
