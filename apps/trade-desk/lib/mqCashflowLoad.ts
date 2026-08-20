/**
 * サーバー側: 資金繰り Engine 入力を Supabase から組み立てる
 */

import type { EntityFilter } from "./mqAggregate";
import type { FinanceTxnLite, MqAccountMapRow } from "./mqZaimMap";
import type { CashflowClassifyRuleRow, TxnOverrideRow } from "./mqCashflowClassify";
import type { CashflowEngineContext } from "./mqCashflowEngine";
import { buildCashflowWithCarry } from "./mqCashflowEngine";
import type { CashflowActionRow, CashflowAdjustmentRow } from "./mqCashflowManual";
import {
  DEFAULT_CORPORATE_CASHFLOW_SETTINGS,
  type MqCashflowSettingsRow,
} from "./mqCashflowSettings";
import { fetchFinanceTxnsRange } from "./mqIngestDb";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Sb = any;

export async function loadCashflowEngineContext(
  sb: Sb,
  opts: {
    year: number;
    entity: EntityFilter;
    businessLine?: string;
  }
): Promise<{
  ctx: CashflowEngineContext;
  adjustments: CashflowAdjustmentRow[];
  actions: CashflowActionRow[];
}> {
  const businessLine = opts.businessLine || "realestate";
  const year = opts.year;
  const entity = opts.entity;

  const [
    settingsRes,
    rulesRes,
    overridesRes,
    adjRes,
    actRes,
    mapsRes,
    loanRes,
  ] = await Promise.all([
    sb.from("kurashift_mq_cashflow_settings").select("*"),
    sb.from("kurashift_mq_cashflow_classify_rules").select("*"),
    sb
      .from("kurashift_mq_cashflow_txn_overrides")
      .select("txn_id,business_line,cashflow_column,note"),
    sb.from("kurashift_mq_cashflow_adjustments").select("*"),
    sb.from("kurashift_mq_cashflow_actions").select("*").eq("is_active", true),
    sb
      .from("kurashift_mq_account_map")
      .select(
        "business_line,entity_match,category_match,subcategory_match,mq_element,combine_treatment,note,priority,approved"
      )
      .eq("approved", true),
    sb
      .from("kurashift_loan_tracker_loans")
      .select("monthly_payment_jpy"),
  ]);

  const settingsRows = (settingsRes.data ?? []) as MqCashflowSettingsRow[];
  if (settingsRows.length === 0 && entity === "corporate") {
    settingsRows.push({
      business_line: DEFAULT_CORPORATE_CASHFLOW_SETTINGS.businessLine,
      entity: DEFAULT_CORPORATE_CASHFLOW_SETTINGS.entity,
      origin_month: `${DEFAULT_CORPORATE_CASHFLOW_SETTINGS.originMonth}-01`,
      initial_cash_man: DEFAULT_CORPORATE_CASHFLOW_SETTINGS.initialCashMan,
      note: DEFAULT_CORPORATE_CASHFLOW_SETTINGS.note,
    });
  }

  const originYear = settingsRows.reduce((min, r) => {
    const y = Number(String(r.origin_month).slice(0, 4));
    return Number.isFinite(y) ? Math.min(min, y) : min;
  }, year);

  const txns = await fetchFinanceTxnsRange(sb, originYear, year);

  const loanYen = (loanRes.data ?? []).reduce(
    (sum: number, r: { monthly_payment_jpy?: number }) => {
      const v = Number(r.monthly_payment_jpy ?? 0);
      return sum + (Number.isFinite(v) ? v : 0);
    },
    0
  );
  const loanMonthlyPaymentMan =
    loanYen > 0 ? Math.round(loanYen / 10_000) : null;

  const adjustments = (adjRes.data ?? []) as CashflowAdjustmentRow[];
  const actions = (actRes.data ?? []) as CashflowActionRow[];

  const ctx: CashflowEngineContext = {
    businessLine,
    entity,
    settingsRows,
    txnOverrides: (overridesRes.data ?? []) as TxnOverrideRow[],
    classifyRules: (rulesRes.data ?? []) as CashflowClassifyRuleRow[],
    loanMonthlyPaymentMan,
    txns: txns as FinanceTxnLite[],
    maps: (mapsRes.data ?? []) as MqAccountMapRow[],
    adjustments,
    actions,
    factsCashByMonthByYear: {},
  };

  return { ctx, adjustments, actions };
}

export async function buildCashflowYearFromDb(
  sb: Sb,
  opts: {
    year: number;
    entity: EntityFilter;
    businessLine?: string;
  }
) {
  const loaded = await loadCashflowEngineContext(sb, opts);
  const built = buildCashflowWithCarry(loaded.ctx, opts.year);
  return { ...loaded, ...built };
}
