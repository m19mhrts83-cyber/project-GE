import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import type { EntityFilter } from "@/lib/mqAggregate";
import type { CashflowColumnKey } from "@/lib/mqCashflowColumns";
import type { CashflowClassifyRuleRow, TxnOverrideRow } from "@/lib/mqCashflowClassify";
import {
  buildCashflowLineItems,
  buildCellDetailResponse,
  type LoanTrackerLite,
} from "@/lib/mqCashflowLineItems";
import { fetchFinanceTxnsRange } from "@/lib/mqIngestDb";
import type { MqCashflowSettingsRow } from "@/lib/mqCashflowSettings";
import { DEFAULT_CORPORATE_CASHFLOW_SETTINGS } from "@/lib/mqCashflowSettings";

function parseColumn(raw: string | null): CashflowColumnKey | null {
  const allowed = [
    "sales",
    "borrow_lt",
    "borrow_st",
    "borrow_officer",
    "repair",
    "advertising",
    "expense",
    "management",
    "acquisition",
    "tax_accountant",
    "loan_repayment",
    "annual_tax",
    "interest_yearend",
    "tax_payment",
    "action_inflow",
  ];
  return allowed.includes(String(raw)) ? (raw as CashflowColumnKey) : null;
}

export async function GET(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const url = new URL(req.url);
  const month = String(url.searchParams.get("month") || "").slice(0, 7);
  const columnKey = parseColumn(url.searchParams.get("column"));
  const entity = (url.searchParams.get("entity") || "corporate") as EntityFilter;
  const businessLine = String(url.searchParams.get("line") || "realestate");
  const cellTotalRaw = url.searchParams.get("cellTotalMan");
  const cellTotalMan =
    cellTotalRaw != null && cellTotalRaw !== ""
      ? Number(cellTotalRaw)
      : null;

  if (!month || month.length < 7 || !columnKey) {
    return NextResponse.json(
      { error: "month and column required" },
      { status: 400 }
    );
  }

  const year = Number(month.slice(0, 4));

  const { data: settingsRaw } = await supabase
    .from("kurashift_mq_cashflow_settings")
    .select("*");
  const { data: rulesRaw } = await supabase
    .from("kurashift_mq_cashflow_classify_rules")
    .select("*");
  const { data: overridesRaw } = await supabase
    .from("kurashift_mq_cashflow_txn_overrides")
    .select("txn_id,business_line,cashflow_column,note");
  const { data: loanRaw } = await supabase
    .from("kurashift_loan_tracker_loans")
    .select("id,name,lender,monthly_payment_jpy");

  const settingsRows = (settingsRaw ?? []) as MqCashflowSettingsRow[];
  if (
    settingsRows.length === 0 &&
    entity === "corporate"
  ) {
    settingsRows.push({
      business_line: DEFAULT_CORPORATE_CASHFLOW_SETTINGS.businessLine,
      entity: DEFAULT_CORPORATE_CASHFLOW_SETTINGS.entity,
      origin_month: `${DEFAULT_CORPORATE_CASHFLOW_SETTINGS.originMonth}-01`,
      initial_cash_man: DEFAULT_CORPORATE_CASHFLOW_SETTINGS.initialCashMan,
    });
  }

  const originYear = settingsRows.reduce((min, r) => {
    const y = Number(String(r.origin_month).slice(0, 4));
    return Number.isFinite(y) ? Math.min(min, y) : min;
  }, year);

  const txns = await fetchFinanceTxnsRange(supabase, originYear, year);

  const loanMonthlyPaymentYen = (loanRaw ?? []).reduce((sum, r) => {
    const v = Number((r as { monthly_payment_jpy?: number }).monthly_payment_jpy ?? 0);
    return sum + (Number.isFinite(v) ? v : 0);
  }, 0);
  const loanMonthlyPaymentMan =
    loanMonthlyPaymentYen > 0
      ? Math.round(loanMonthlyPaymentYen / 10_000)
      : null;

  const lineItems = buildCashflowLineItems({
    year,
    entity,
    businessLine,
    txns,
    txnOverrides: (overridesRaw ?? []) as TxnOverrideRow[],
    classifyRules: (rulesRaw ?? []) as CashflowClassifyRuleRow[],
    loanTracker: (loanRaw ?? []) as LoanTrackerLite[],
    loanMonthlyPaymentMan,
  });

  const detail = buildCellDetailResponse({
    month,
    columnKey,
    cellTotalMan,
    items: lineItems,
  });

  return NextResponse.json({ ok: true, ...detail });
}
