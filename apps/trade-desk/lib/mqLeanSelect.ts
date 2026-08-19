/**
 * MQ period facts の lean select（select("*") 回避）
 * 画面・合成で使う列だけ。payload 等の肥大列を引かない。
 */
export const MQ_FACT_SELECT =
  "id,business_line,entity,period_month,scenario_kind,plan_variant_id,q,pq,vq,f,f_annual,cash_in,cash_out,cash_end,depreciation_jpy";

/** B/S スナップの lean select */
export const MQ_BS_SELECT =
  "business_line,entity,as_of_date,cash,receivables,inventory,fixed_assets,liabilities_st,liabilities_lt,capital,retained_earnings,current_profit,note,source";

/** 申告KPI（比較帯で使う列） */
export const TAX_YEAR_METRICS_SELECT =
  "scope,fiscal_year,filing_status,filed_on,taxable_income_jpy,income_tax_jpy,refund_or_pay,revenue_jpy,ordinary_income_jpy,corporate_tax_jpy,tax_payable_jpy,payload,note,source";
