import Shell from "@/components/Shell";
import MqBsPanel from "@/components/MqBsPanel";
import MqCompareBars from "@/components/MqCompareBars";
import MqCashflowWorkspace from "@/components/MqCashflowWorkspace";
import MqReconcilePanel from "@/components/MqReconcilePanel";
import MqTaxComparePanel from "@/components/MqTaxComparePanel";
import MqFactsForm from "@/components/MqFactsForm";
import MqPlanForm from "@/components/MqPlanForm";
import MqZaimIngestPanel from "@/components/MqZaimIngestPanel";
import MqStrackPanel from "@/components/MqStrackPanel";
import { fmtMqMan } from "@/lib/mqUnits";
import {
  aggregatePlanAnnual,
  aggregateRows,
  availableMonths,
  availableYears,
  entityLabel,
  filterFactsMonth,
  filterFactsYearActual,
  filterPlans,
  lineLabel,
  listPlanVariants,
  metricBars,
  scaleAnnualComputedToMonth,
  type CompareMode,
  type EntityFilter,
  type GrainFilter,
  type LineFilter,
  type MqFactRow,
} from "@/lib/mqAggregate";
import {
  combineBs,
  monthEndDate,
  normalizeBs,
  pickNearestBs,
  yearEndDate,
  type MqBsFields,
  type MqBsRow,
} from "@/lib/mqBs";
import { sumLoanTrackerLt } from "@/lib/mqLoanSuggest";
import { qUnitLabel } from "@/lib/mqPolicy";
import { computeMq, type MqComputed } from "@/lib/mqEquations";
import type { MqAccountMapRow } from "@/lib/mqZaimMap";
import { buildMqTaxCompare, buildMqTaxCompareDual } from "@/lib/mqTaxCompare";
import type { TaxYearMetricRow } from "@/lib/taxInsights";
import {
  aggregateReCfFromCategoryYear,
  type FinanceCategoryYearRow,
} from "@/lib/reFinanceYtd";
import { createClient } from "@/lib/supabase/server";
import { fetchAllMqPeriodFacts } from "@/lib/mqFactsFetch";
import { fetchFinanceTxnsRange } from "@/lib/mqIngestDb";
import MqLaneNav, { type MqView as MqLaneView } from "@/components/MqLaneNav";
import {
  MQ_BS_SELECT,
  TAX_YEAR_METRICS_SELECT,
} from "@/lib/mqLeanSelect";
import MqPeriodLinks from "@/components/MqPeriodLinks";
import { type MqCashflowMonthRow } from "@/lib/mqCashflow";
import {
  buildCashflowWithCarry,
  negativeMonths,
} from "@/lib/mqCashflowEngine";
import {
  DEFAULT_CORPORATE_CASHFLOW_SETTINGS,
  type MqCashflowSettingsRow,
} from "@/lib/mqCashflowSettings";
import {
  buildReconcileDiffs,
  projectCashflowToMqBs,
} from "@/lib/mqCashflowProject";
import type {
  CashflowClassifyRuleRow,
  TxnOverrideRow,
} from "@/lib/mqCashflowClassify";
import type {
  CashflowActionRow,
  CashflowAdjustmentRow,
} from "@/lib/mqCashflowManual";
import { pickYearendAdjustment } from "@/lib/mqCashflowManual";
import {
  buildEquityTrend,
  combineProjectedEquityBs,
  yearsForEquityTrend,
} from "@/lib/mqEquityTrend";
import MqEquityTrendPanel from "@/components/MqEquityTrendPanel";
import MqMetricsTrendPlaceholder from "@/components/MqMetricsTrendPlaceholder";

export const dynamic = "force-dynamic";

type Sp = Record<string, string | string[] | undefined>;
type MqView = MqLaneView;

function one(sp: Sp, key: string, fallback: string): string {
  const v = sp[key];
  if (Array.isArray(v)) return v[0] || fallback;
  return v || fallback;
}

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

type Panel = {
  title: string;
  computed: MqComputed | null;
  cashBegin?: number | null;
  cashIn?: number | null;
  cashOut?: number | null;
  cashEnd?: number | null;
  depreciation?: number | null;
  /** F 固定費の内訳（クリックで確認用） */
  fMonthlyPart?: number | null;
  fAnnualAllocated?: number | null;
  /** 表示粒度（month=年額÷12 / year=年額側） */
  fBreakdownKind?: "month" | "year";
  emptyHint: string;
  fNote?: string;
};

function yenToManRounded(yen: number): number {
  return Math.round((Number(yen) || 0) / 10000);
}

function annualFactCoverageLabel(rows: MqFactRow[], year: string): string | null {
  const months = Array.from(
    new Set(
      rows
        .filter((r) => String(r.period_month).slice(0, 4) === year.slice(0, 4))
        .map((r) => String(r.period_month).slice(5, 7))
    )
  ).sort();
  if (!months.length) return null;
  if (months.length >= 12) return "通年";
  return `1-${String(Number(months[months.length - 1]))}月`;
}

export default async function MqPage({
  searchParams,
}: {
  searchParams: Promise<Sp>;
}) {
  const sp = await searchParams;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const line = one(sp, "line", "realestate") as LineFilter;
  const entity = one(sp, "entity", "combined") as EntityFilter;
  const grain = one(sp, "grain", "year") as GrainFilter;
  const mode = one(sp, "mode", "aa") as CompareMode;
  const view = one(sp, "view", "mq") as MqView;

  const { data: bsRaw } = await supabase
    .from("kurashift_mq_bs_snapshots")
    .select(MQ_BS_SELECT)
    .order("as_of_date", { ascending: false })
    .limit(120);

  const { data: loanRaw } = await supabase
    .from("kurashift_loan_tracker_loans")
    .select(
      "balance_jpy,monthly_payment_jpy,annual_payment_jpy, category_major, tags, name"
    );

  const { data: taxMetricsRaw } = await supabase
    .from("kurashift_tax_year_metrics")
    .select(TAX_YEAR_METRICS_SELECT)
    .order("fiscal_year", { ascending: false })
    .limit(24);

  const { data: accountMapRaw } = await supabase
    .from("kurashift_mq_account_map")
    .select(
      "business_line,entity_match,category_match,subcategory_match,mq_element,combine_treatment,note,priority,approved"
    )
    .eq("approved", true)
    .order("priority", { ascending: true });

  const { data: cashflowSettingsRaw } = await supabase
    .from("kurashift_mq_cashflow_settings")
    .select("*");

  const { data: cashflowRulesRaw } = await supabase
    .from("kurashift_mq_cashflow_classify_rules")
    .select("*");

  const { data: cashflowOverridesRaw } = await supabase
    .from("kurashift_mq_cashflow_txn_overrides")
    .select("txn_id,business_line,cashflow_column,note");

  const { data: cashflowAdjustmentsRaw } = await supabase
    .from("kurashift_mq_cashflow_adjustments")
    .select("*");

  const { data: cashflowActionsRaw } = await supabase
    .from("kurashift_mq_cashflow_actions")
    .select("*")
    .eq("is_active", true);

  const { data: financeCategoryYearRaw } = await supabase
    .from("kurashift_finance_category_year")
    .select("fiscal_year,category,income_jpy,expense_jpy,net_jpy")
    .order("fiscal_year", { ascending: false })
    .limit(400);

  const { count: propertyUnitCount } = await supabase
    .from("property_units")
    .select("property_id", { count: "exact", head: true })
    .eq("status", "occupied");

  let rows: MqFactRow[];
  let error: Error | null = null;
  try {
    rows = await fetchAllMqPeriodFacts(supabase);
  } catch (e) {
    rows = [];
    error = e instanceof Error ? e : new Error(String(e));
  }
  const bsRows = (bsRaw ?? []) as MqBsRow[];
  const loanTrackerLt = sumLoanTrackerLt(loanRaw ?? []);
  const loanMonthlyPaymentYen = (loanRaw ?? []).reduce((sum, r) => {
    const v = Number((r as any).monthly_payment_jpy ?? 0);
    return sum + (Number.isFinite(v) ? v : 0);
  }, 0);
  const loanMonthlyPaymentMan =
    loanMonthlyPaymentYen > 0 ? yenToManRounded(loanMonthlyPaymentYen) : null;
  const months = availableMonths(rows);
  const years = availableYears(rows);
  const bsYears = Array.from(
    new Set((bsRaw ?? []).map((r) => String(r.as_of_date).slice(0, 4)))
  ).sort();
  const financeYears = Array.from(
    new Set((financeCategoryYearRaw ?? []).map((r) => String(r.fiscal_year)))
  ).sort();
  const taxYears = Array.from(
    new Set((taxMetricsRaw ?? []).map((r) => String(r.fiscal_year)))
  ).sort();
  const yearsAll = Array.from(
    new Set([...years, ...bsYears, ...financeYears, ...taxYears])
  )
    .sort()
    .reverse();
  const defaultMonth = months[0] || currentMonth();
  const defaultYear = yearsAll[0] || String(new Date().getFullYear());
  const variants = listPlanVariants(rows);
  const defaultVariant = variants[0] || "基本";
  const financeCategoryYearRows = (financeCategoryYearRaw ?? []) as FinanceCategoryYearRow[];
  const annualQRealestate = propertyUnitCount && propertyUnitCount > 0 ? propertyUnitCount : null;

  const periodA =
    grain === "year"
      ? one(sp, "a", defaultYear).slice(0, 4)
      : one(sp, "a", defaultMonth).slice(0, 7);
  const periodB =
    grain === "year"
      ? one(sp, "b", yearsAll[1] || defaultYear).slice(0, 4)
      : one(sp, "b", months[1] || defaultMonth).slice(0, 7);
  const planYear = one(sp, "py", periodA.length === 4 ? periodA : periodA.slice(0, 4));
  const variantA = one(sp, "va", defaultVariant);
  const variantB = one(sp, "vb", variants[1] || defaultVariant);

  const cashflowYear = Number(periodA.slice(0, 4));

  let cashflowRows: MqCashflowMonthRow[] = [];
  let cashflowNegative: { month: string; cashEndMan: number }[] = [];
  let cashflowOriginHint: string | null = null;
  let cashflowAdjustments: CashflowAdjustmentRow[] = [];
  let cashflowActions: CashflowActionRow[] = [];
  let cashflowInterestMan: number | null = null;
  let cashflowTaxMan: number | null = null;
  let cashflowTaxAccrual: "december" | "payment" = "december";
  let cashflowL1Begin: number | null = null;
  let cashflowL1End: number | null = null;
  let cashflowL1In: number | null = null;
  let cashflowL1Out: number | null = null;
  let reconcileProject: ReturnType<typeof projectCashflowToMqBs> | null = null;
  let reconcileDiffs: ReturnType<typeof buildReconcileDiffs> = [];
  const equityProjectedByYear: Record<number, MqBsFields> = {};
  let equityOriginYear: number | null = null;

  function buildActual(period: string) {
    const subset =
      grain === "year"
        ? filterFactsYearActual(rows, line, entity, period)
        : filterFactsMonth(rows, line, entity, period);
    const agg = aggregateRows(subset, grain === "year" ? "year" : "month");
    if (
      grain === "year" &&
      line === "realestate" &&
      annualQRealestate != null &&
      agg.computed
    ) {
      return {
        ...agg,
        computed: computeMq({
          pq: agg.input.pq,
          vq: agg.input.vq,
          f: agg.input.f,
          q: annualQRealestate,
        }),
      };
    }
    if (subset.length > 0 || grain !== "year" || line !== "realestate") {
      return agg;
    }
    const cf = aggregateReCfFromCategoryYear(
      financeCategoryYearRows,
      Number(period.slice(0, 4))
    );
    const bucket =
      entity === "personal"
        ? cf.personal
        : entity === "corporate"
          ? cf.corporate
          : cf.combined;
    if (!bucket.income && !bucket.expense) return agg;
    const fallbackInput = {
      pq: yenToManRounded(bucket.income),
      vq: 0,
      f: yenToManRounded(bucket.expense),
      q: annualQRealestate,
    };
    return {
      input: fallbackInput,
      computed: computeMq(fallbackInput),
      cashIn: yenToManRounded(bucket.income),
      cashOut: yenToManRounded(bucket.expense),
      cashEnd: null,
      depreciation: null,
      byLine: [],
      fMonthlyPart: yenToManRounded(bucket.expense),
      fAnnualAllocated: 0,
    };
  }

  function buildPlan(year: string, variant: string, asMonth: boolean) {
    const subset = filterPlans(rows, line, entity, year, variant);
    const ann = aggregatePlanAnnual(subset);
    if (!ann.computed) {
      return {
        ...ann,
        computed: null as MqComputed | null,
      };
    }
    return {
      ...ann,
      computed: asMonth
        ? scaleAnnualComputedToMonth(ann.computed)
        : ann.computed,
    };
  }

  let left: Panel;
  let right: Panel;
  let byLine = aggregateRows(
    grain === "year"
      ? filterFactsYearActual(rows, line, entity, periodA)
      : filterFactsMonth(rows, line, entity, periodA),
    grain === "year" ? "year" : "month"
  ).byLine;

  if (mode === "aa") {
    const a = buildActual(periodA);
    const b = buildActual(periodB);
    const aCoverage =
      grain === "year" ? annualFactCoverageLabel(filterFactsYearActual(rows, line, entity, periodA), periodA) : null;
    const bCoverage =
      grain === "year" ? annualFactCoverageLabel(filterFactsYearActual(rows, line, entity, periodB), periodB) : null;
    const aFallback =
      grain === "year" &&
      filterFactsYearActual(rows, line, entity, periodA).length === 0 &&
      a.computed != null;
    const bFallback =
      grain === "year" &&
      filterFactsYearActual(rows, line, entity, periodB).length === 0 &&
      b.computed != null;
    left = {
      title:
        grain === "year"
          ? `実績 ${periodA}${aFallback ? "（年次補完）" : aCoverage ? `（${aCoverage}実績）` : ""}`
          : `実績 ${periodA}`,
      computed: a.computed,
      cashIn: a.cashIn,
      cashOut: a.cashOut,
      cashEnd: a.cashEnd,
      depreciation: a.depreciation,
      fMonthlyPart: a.computed ? a.fMonthlyPart : null,
      fAnnualAllocated: a.computed ? a.fAnnualAllocated : null,
      fBreakdownKind: grain === "month" ? "month" : "year",
      emptyHint:
        "この条件の実績がありません。下の月次フォームで保存してください（年次は月次実績の合算表示です）。",
      fNote:
        grain === "month" && a.computed
          ? `F内訳: 月額 ${fmtMqMan(a.fMonthlyPart)} + 年額÷12 ${fmtMqMan(a.fAnnualAllocated)}`
          : undefined,
    };
    right = {
      title:
        grain === "year"
          ? `実績 ${periodB}${bFallback ? "（年次補完）" : bCoverage ? `（${bCoverage}実績）` : ""}`
          : `実績 ${periodB}`,
      computed: b.computed,
      cashIn: b.cashIn,
      cashOut: b.cashOut,
      cashEnd: b.cashEnd,
      depreciation: b.depreciation,
      fMonthlyPart: b.computed ? b.fMonthlyPart : null,
      fAnnualAllocated: b.computed ? b.fAnnualAllocated : null,
      fBreakdownKind: grain === "month" ? "month" : "year",
      emptyHint: "比較用のもう一方の実績がありません。",
    };
  } else if (mode === "ap") {
    const a = buildActual(periodA);
    const p = buildPlan(planYear, variantA, grain === "month");
    left = {
      title: `実績 ${periodA}`,
      computed: a.computed,
      cashIn: a.cashIn,
      cashOut: a.cashOut,
      cashEnd: a.cashEnd,
      depreciation: a.depreciation,
      fMonthlyPart: a.computed ? a.fMonthlyPart : null,
      fAnnualAllocated: a.computed ? a.fAnnualAllocated : null,
      fBreakdownKind: grain === "month" ? "month" : "year",
      emptyHint: "実績がありません。",
    };
    right = {
      title: `計画「${variantA}」${planYear}${grain === "month" ? "（÷12）" : ""}`,
      computed: p.computed,
      fMonthlyPart: p.computed ? p.fMonthlyPart : null,
      fAnnualAllocated: p.computed ? p.fAnnualAllocated : null,
      fBreakdownKind: grain === "month" ? "month" : "year",
      emptyHint: "この計画がありません。下の年次計画フォームで保存してください。",
    };
  } else {
    const p1 = buildPlan(planYear, variantA, grain === "month");
    const p2 = buildPlan(planYear, variantB, grain === "month");
    left = {
      title: `計画「${variantA}」${planYear}${grain === "month" ? "（÷12）" : ""}`,
      computed: p1.computed,
      fMonthlyPart: p1.computed ? p1.fMonthlyPart : null,
      fAnnualAllocated: p1.computed ? p1.fAnnualAllocated : null,
      fBreakdownKind: grain === "month" ? "month" : "year",
      emptyHint: "計画Aがありません。",
    };
    right = {
      title: `計画「${variantB}」${planYear}${grain === "month" ? "（÷12）" : ""}`,
      computed: p2.computed,
      fMonthlyPart: p2.computed ? p2.fMonthlyPart : null,
      fAnnualAllocated: p2.computed ? p2.fAnnualAllocated : null,
      fBreakdownKind: grain === "month" ? "month" : "year",
      emptyHint: "計画Bがありません。別パターン名で保存してください。",
    };
    byLine = [];
  }

  function href(next: Record<string, string>) {
    const p = new URLSearchParams({
      line,
      entity,
      grain,
      mode,
      view,
      a: periodA,
      b: periodB,
      py: planYear,
      va: variantA,
      vb: variantB,
      ...next,
    });
    return `/mq?${p.toString()}`;
  }

  const cashflowDisplayYear = periodA.slice(0, 4);

  const formMonth = grain === "month" ? periodA : defaultMonth;

  const bsAsOf =
    grain === "year" ? yearEndDate(periodA) : monthEndDate(periodA);
  const bsLine =
    line === "ai" ? "ai" : line === "realestate" ? "realestate" : "realestate";
  const requireInventory = line === "ai";

  let bsFields = null as ReturnType<typeof normalizeBs> | null;
  let bsCombineNote: string | null = null;
  let bsFormEntity: "personal" | "corporate" =
    entity === "corporate" ? "corporate" : "personal";
  let bsInitial: Partial<ReturnType<typeof normalizeBs>> & {
    note?: string | null;
  } = {};

  if (line === "all") {
    bsCombineNote =
      "事業線「全体」のB/Sは未対応です。不動産またはAIを選んで入力してください。";
  } else if (entity === "combined") {
    const pers = pickNearestBs(bsRows, bsLine, "personal", bsAsOf);
    const corp = pickNearestBs(bsRows, bsLine, "corporate", bsAsOf);
    if (!pers && !corp) {
      bsCombineNote = "個人・法人ともスナップがありません。片方ずつ穴埋めしてください。";
    } else if (!pers || !corp) {
      bsCombineNote =
        "合算には個人・法人の両方のスナップが必要です（いまは片方のみ表示）。";
      const one = pers || corp!;
      bsFields = normalizeBs(one);
      bsFormEntity = one.entity === "corporate" ? "corporate" : "personal";
      bsInitial = { ...bsFields, note: one.note };
    } else {
      bsFields = combineBs(normalizeBs(pers), normalizeBs(corp));
      bsFormEntity = "personal";
      bsInitial = { ...normalizeBs(pers), note: pers.note };
      bsCombineNote =
        "合算表示。穴埋めは主体を選んで個別保存（片側の欠損は合算でも要確認）。";
    }
  } else {
    const hit = pickNearestBs(bsRows, bsLine, entity, bsAsOf);
    if (hit) {
      bsFields = normalizeBs(hit);
      bsFormEntity = entity;
      bsInitial = { ...bsFields, note: hit.note };
      if (String(hit.as_of_date).slice(0, 10) !== bsAsOf) {
        bsCombineNote = `直近スナップ ${String(hit.as_of_date).slice(0, 10)} を表示（基準 ${bsAsOf}）`;
      }
    } else {
      bsFormEntity = entity;
      bsCombineNote = "この条件のB/Sスナップがありません。下の穴埋めで作成できます。";
    }
  }

  const yearForCarry = (grain === "year" ? periodA : periodA.slice(0, 4)).slice(
    0,
    4
  );
  const priorYear = String(Number(yearForCarry) - 1);
  const priorYearEnd = yearEndDate(priorYear);
  let priorYearCash: number | null = null;
  let priorYearAsOf: string | null = null;
  if (line !== "all") {
    if (entity === "combined") {
      const p = pickNearestBs(bsRows, bsLine, "personal", priorYearEnd);
      const c = pickNearestBs(bsRows, bsLine, "corporate", priorYearEnd);
      const combined = combineBs(
        p ? normalizeBs(p) : null,
        c ? normalizeBs(c) : null
      );
      if (combined?.cash != null) {
        priorYearCash = combined.cash;
        priorYearAsOf = priorYearEnd;
      }
    } else {
      const prev = pickNearestBs(bsRows, bsLine, entity, priorYearEnd);
      if (prev?.cash != null) {
        priorYearCash = Number(prev.cash);
        priorYearAsOf = String(prev.as_of_date).slice(0, 10);
      }
    }
  }

  /** 現金橋の前期繰越: 年次=前年B/S現金、月次=前月末 facts.cash_end */
  function cashBeginFor(period: string): number | null {
    if (grain === "year" && cashflowL1Begin != null) {
      return cashflowL1Begin;
    }
    if (grain === "year") {
      return priorYearCash;
    }
    const [y, m] = period.slice(0, 7).split("-").map(Number);
    const prev = new Date(Date.UTC(y, m - 2, 1));
    const prevKey = `${prev.getUTCFullYear()}-${String(prev.getUTCMonth() + 1).padStart(2, "0")}`;
    const subset = filterFactsMonth(rows, line, entity, prevKey);
    const agg = aggregateRows(subset, "month");
    return agg.cashEnd;
  }

  const qLabel = line === "all" ? undefined : qUnitLabel(line);

  const accountMapRows = (accountMapRaw ?? []) as MqAccountMapRow[];

  // 月次資金繰り表（L1 帳簿 · 起点設定 · 翌年繰越）
  if (line === "realestate") {
    const businessLine = "realestate";
    const settingsRows = (cashflowSettingsRaw ??
      []) as MqCashflowSettingsRow[];
    if (
      settingsRows.length === 0 &&
      entity === "corporate"
    ) {
      settingsRows.push({
        id: "default",
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
    }, cashflowYear);

    const factsCashByMonthByYear: Record<
      number,
      Record<
        string,
        {
          cashInMan: number | null;
          cashOutMan: number | null;
          cashEndMan: number | null;
        }
      >
    > = {};

    for (let y = originYear; y <= cashflowYear; y++) {
      const monthsY = Array.from({ length: 12 }, (_, i) => {
        return `${y}-${String(i + 1).padStart(2, "0")}`;
      });
      const byMonth: Record<
        string,
        {
          cashInMan: number | null;
          cashOutMan: number | null;
          cashEndMan: number | null;
        }
      > = {};
      for (const mo of monthsY) {
        const subset = filterFactsMonth(rows, line, entity, mo);
        const agg = aggregateRows(subset, "month");
        byMonth[mo] = {
          cashInMan: agg.cashIn,
          cashOutMan: agg.cashOut,
          cashEndMan: agg.cashEnd,
        };
      }
      factsCashByMonthByYear[y] = byMonth;
    }

    const txns = await fetchFinanceTxnsRange(
      supabase,
      originYear,
      cashflowYear
    );

    const bsFallbackOpeningByYear: Record<number, number | null> = {
      [cashflowYear]: priorYearCash,
    };

    cashflowAdjustments = (cashflowAdjustmentsRaw ?? []) as CashflowAdjustmentRow[];
    cashflowActions = (cashflowActionsRaw ?? []) as CashflowActionRow[];

    const engineCtx = {
      businessLine,
      entity,
      settingsRows,
      txnOverrides: (cashflowOverridesRaw ?? []) as TxnOverrideRow[],
      classifyRules: (cashflowRulesRaw ?? []) as CashflowClassifyRuleRow[],
      loanMonthlyPaymentMan,
      txns,
      maps: accountMapRows,
      adjustments: cashflowAdjustments,
      actions: cashflowActions,
      factsCashByMonthByYear,
      bsFallbackOpeningByYear,
    };

    const built = buildCashflowWithCarry(engineCtx, cashflowYear);

    cashflowRows = built.rows;
    cashflowNegative = negativeMonths(cashflowRows);
    cashflowL1Begin = built.rows[0]?.cashBeginMan ?? built.openingCashMan;
    cashflowL1End =
      built.rows[built.rows.length - 1]?.cashEndMan ?? null;
    cashflowL1In = built.rows.reduce((s, r) => s + (r.salesMan ?? 0) + (r.borrowLtMan ?? 0) + (r.borrowStMan ?? 0) + (r.borrowOfficerMan ?? 0) + (r.actionInflowMan ?? 0), 0);
    cashflowL1Out = built.rows.reduce((s, r) => {
      const parts = [
        r.repairMan, r.advertisingMan, r.expenseMan, r.managementMan,
        r.acquisitionMan, r.taxAccountantMan, r.annualTaxMan, r.loanRepaymentMan,
        r.interestYearendMan, r.taxPaymentMan,
      ];
      return s + parts.reduce<number>((a, p) => a + (p ?? 0), 0);
    }, 0);

    if (entity === "personal" || entity === "corporate") {
      const interest = pickYearendAdjustment(cashflowAdjustments, {
        businessLine,
        entity,
        year: cashflowYear,
        field: "interest_yearend",
      });
      const tax = pickYearendAdjustment(cashflowAdjustments, {
        businessLine,
        entity,
        year: cashflowYear,
        field: "tax_payment",
      });
      cashflowInterestMan = interest ? Number(interest.amount_man) : null;
      cashflowTaxMan = tax ? Number(tax.amount_man) : null;
      cashflowTaxAccrual =
        built.settings?.taxAccrualMonth === "payment" ? "payment" : "december";

      reconcileProject = projectCashflowToMqBs({
        year: cashflowYear,
        rows: built.rows,
        settings: built.settings,
      });
      const subset = filterFactsYearActual(
        rows,
        "realestate",
        entity,
        String(cashflowYear)
      );
      const agg = aggregateRows(subset, "year");
      const bsSnap = pickNearestBs(
        bsRows,
        "realestate",
        entity,
        yearEndDate(String(cashflowYear))
      );
      reconcileDiffs = buildReconcileDiffs({
        project: reconcileProject,
        factsAnnual: {
          pq: agg.computed?.pq ?? null,
          vq: agg.computed?.vq ?? null,
          f: agg.computed?.f ?? null,
          cash_in: agg.cashIn,
          cash_out: agg.cashOut,
          cash_end: agg.cashEnd,
        },
        bsSnap: bsSnap
          ? {
              cash: normalizeBs(bsSnap).cash,
              current_profit: normalizeBs(bsSnap).current_profit,
            }
          : null,
      });
    }

    if (built.settings) {
      cashflowOriginHint = `起点: ${built.settings.originMonth} 期首 ${fmtMqMan(built.settings.initialCashMan)}（${built.settings.note || "設定"}）`;
    } else if (built.openingCashMan != null) {
      cashflowOriginHint = `${cashflowDisplayYear}年1月 期首 ${fmtMqMan(built.openingCashMan)}（前年末繰越）`;
    }

    equityOriginYear = originYear;
    for (let y = originYear; y <= cashflowYear; y++) {
      if (entity === "combined") {
        const corp = buildCashflowWithCarry(
          { ...engineCtx, entity: "corporate" },
          y
        );
        const pers = buildCashflowWithCarry(
          { ...engineCtx, entity: "personal" },
          y
        );
        const combined = combineProjectedEquityBs(
          projectCashflowToMqBs({
            year: y,
            rows: pers.rows,
            settings: pers.settings,
          }).bs,
          projectCashflowToMqBs({
            year: y,
            rows: corp.rows,
            settings: corp.settings,
          }).bs
        );
        if (combined) equityProjectedByYear[y] = combined;
      } else if (entity === "personal" || entity === "corporate") {
        const builtY =
          y === cashflowYear ? built : buildCashflowWithCarry(engineCtx, y);
        equityProjectedByYear[y] = projectCashflowToMqBs({
          year: y,
          rows: builtY.rows,
          settings: builtY.settings,
        }).bs;
      }
    }
  }

  const trendLine = line === "ai" ? "ai" : line === "realestate" ? "realestate" : "all";
  const trendYears = yearsForEquityTrend({
    bsRows,
    line: trendLine,
    originYear: equityOriginYear,
    throughYear: cashflowYear,
  });
  const mqGByYear: Record<number, number | null> = {};
  for (const y of trendYears) {
    const subset = filterFactsYearActual(rows, line, entity, String(y));
    mqGByYear[y] = aggregateRows(subset, "year").computed?.g ?? null;
  }
  const equityTrendPoints = buildEquityTrend({
    years: trendYears,
    bsRows,
    line: trendLine,
    entity,
    mqGByYear,
    projectedByYear: equityProjectedByYear,
  });
  const trendYearOptions = Array.from(
    new Set([
      ...trendYears.map(String),
      ...yearsAll.filter(
        (y) => Number(y) >= (equityOriginYear ?? cashflowYear) - 1
      ),
    ])
  )
    .sort()
    .reverse();

  const vqAccountMap = accountMapRows
    .filter((r) => {
      const lineOk = line === "all" ? true : r.business_line === line;
      if (!lineOk) return false;
      const entityOk =
        entity === "combined"
          ? r.entity_match === "" ||
            r.entity_match === "personal" ||
            r.entity_match === "corporate"
          : r.entity_match === "" || r.entity_match === entity;
      if (!entityOk) return false;
      return r.mq_element === "vq";
    })
    .slice(0, 8)
    .map((r) => ({
      category_match: String(r.category_match || ""),
      subcategory_match: String(r.subcategory_match || ""),
      entity_match: String(r.entity_match || ""),
      combine_treatment: String(r.combine_treatment || ""),
      note: r.note ?? null,
    }));

  const taxMetrics = (taxMetricsRaw ?? []) as TaxYearMetricRow[];
  const compareYear = Number(
    (grain === "year" ? periodA : periodA.slice(0, 4)).slice(0, 4)
  );

  function actualFor(ent: "personal" | "corporate") {
    const subset =
      grain === "year"
        ? filterFactsYearActual(rows, line, ent, periodA)
        : filterFactsMonth(rows, line, ent, periodA);
    return aggregateRows(subset, grain === "year" ? "year" : "month");
  }

  const taxCompareDual =
    entity === "combined" && line !== "all" && grain === "year"
      ? buildMqTaxCompareDual({
          line,
          fiscalYear: compareYear,
          personal: {
            computed: actualFor("personal").computed,
            depreciationMan: actualFor("personal").depreciation ?? null,
            metric: taxMetrics.find(
              (m) =>
                m.fiscal_year === compareYear && m.scope === "personal"
            ),
          },
          corporate: {
            computed: actualFor("corporate").computed,
            depreciationMan: actualFor("corporate").depreciation ?? null,
            metric: taxMetrics.find(
              (m) =>
                m.fiscal_year === compareYear && m.scope === "corporate"
            ),
          },
        })
      : null;

  const taxCompare =
    entity !== "combined"
      ? buildMqTaxCompare({
          line,
          entity,
          fiscalYear: compareYear,
          computed: left.computed,
          depreciationMan: left.depreciation ?? null,
          metric: taxMetrics.find(
            (m) =>
              m.fiscal_year === compareYear &&
              m.scope === (entity === "corporate" ? "corporate" : "personal")
          ),
        })
      : null;
  const mqCashMonthly =
    left.cashIn != null && left.cashOut != null ? left.cashIn - left.cashOut : null;
  const mqFundingSignal =
    mqCashMonthly == null
      ? "確認待ち"
      : mqCashMonthly <= 0
        ? "要テコ入れ"
        : mqCashMonthly < 300_000
          ? "注意"
          : "余裕あり";

  return (
    <Shell active="/mq" email={user?.email ?? null}>
      <p className="page-kicker">③ 事業 · MQ</p>
      <h1>MQ会計評価</h1>
      <p className="sub">
        実績は月次でチューニング、計画は年次で立てる。金額は万円（四捨五入）。年額Fは月次で÷12。
        AIのQは案件数。現金は家計含む参考・年別クローズで繰越。
      </p>

      <MqLaneNav
        active={view}
        hrefFor={(v) =>
          href({
            view: v,
            ...(v === "cashflow" || v === "reconcile" || v === "trends"
              ? { grain: "year", a: periodA.slice(0, 4) }
              : {}),
          })
        }
      />

      {error ? (
        <div className="card" style={{ marginTop: 12, borderColor: "var(--high)" }}>
          <p className="meta">読取エラー: {error.message}</p>
        </div>
      ) : null}

      {view === "cashflow" ? (
        <>
          <div className="card" style={{ marginTop: 12 }}>
            <header>
              <span className="lvl">条件</span>
              <strong>資金繰り表 · {cashflowDisplayYear}年</strong>
            </header>
            <div className="mq-slicer" style={{ marginTop: 10 }}>
              <div className="mq-slicer-group">
                <span className="meta">表示年度</span>
                <MqPeriodLinks
                  grain="year"
                  periods={yearsAll.length ? yearsAll : [defaultYear]}
                  current={cashflowDisplayYear}
                  makeHref={(v) => href({ a: v.slice(0, 4), grain: "year", view: "cashflow" })}
                />
              </div>
              <div className="mq-slicer-group">
                <span className="meta">事業線</span>
                {(
                  [
                    ["realestate", "不動産"],
                    ["ai", "AI"],
                    ["all", "全体"],
                  ] as const
                ).map(([v, lab]) => (
                  <a
                    key={v}
                    className={`btn${line === v ? " primary" : ""}`}
                    href={href({ line: v, view: "cashflow" })}
                  >
                    {lab}
                  </a>
                ))}
              </div>
              <div className="mq-slicer-group">
                <span className="meta">主体</span>
                {(
                  [
                    ["personal", "個人"],
                    ["corporate", "法人"],
                    ["combined", "合算"],
                  ] as const
                ).map(([v, lab]) => (
                  <a
                    key={v}
                    className={`btn${entity === v ? " primary" : ""}`}
                    href={href({ entity: v, view: "cashflow" })}
                  >
                    {lab}
                  </a>
                ))}
              </div>
            </div>
            <p className="meta" style={{ marginTop: 8 }}>
              {lineLabel(line)} · {entityLabel(entity)} · {cashflowDisplayYear}年の月次推移（1〜12月）
            </p>
          </div>

          <MqCashflowWorkspace
            title={`${lineLabel(line)} · ${entityLabel(entity)} 月次資金繰り表`}
            year={cashflowDisplayYear}
            rows={cashflowRows}
            grainHint={`${cashflowDisplayYear}年の各月を横に並べ、項目ごとの入出金を一覧できます。`}
            originHint={cashflowOriginHint}
            negativeMonths={cashflowNegative}
            businessLine="realestate"
            entity={entity}
            interactive={line === "realestate"}
            taxEntity={
              entity === "personal" || entity === "corporate" ? entity : null
            }
            interestMan={cashflowInterestMan}
            taxMan={cashflowTaxMan}
            taxAccrualMonth={cashflowTaxAccrual}
            actions={cashflowActions}
            unavailableReason={
              line === "realestate"
                ? null
                : "資金繰り表は現在、不動産ラインで表示します。上の事業線を「不動産」にすると内容が出ます。"
            }
          />
        </>
      ) : view === "reconcile" ? (
        <>
          <div className="card" style={{ marginTop: 12 }}>
            <header>
              <span className="lvl">条件</span>
              <strong>整合 · {cashflowDisplayYear}年</strong>
            </header>
            <div className="mq-slicer" style={{ marginTop: 10 }}>
              <div className="mq-slicer-group">
                <span className="meta">表示年度</span>
                <MqPeriodLinks
                  grain="year"
                  periods={yearsAll.length ? yearsAll : [defaultYear]}
                  current={cashflowDisplayYear}
                  makeHref={(v) =>
                    href({ a: v.slice(0, 4), grain: "year", view: "reconcile" })
                  }
                />
              </div>
              <div className="mq-slicer-group">
                <span className="meta">主体</span>
                {(
                  [
                    ["personal", "個人"],
                    ["corporate", "法人"],
                  ] as const
                ).map(([v, lab]) => (
                  <a
                    key={v}
                    className={`btn${entity === v ? " primary" : ""}`}
                    href={href({ entity: v, view: "reconcile" })}
                  >
                    {lab}
                  </a>
                ))}
              </div>
            </div>
          </div>
          {entity !== "personal" && entity !== "corporate" ? (
            <p className="meta" style={{ marginTop: 12 }}>
              整合は法人または個人を選んでください。
            </p>
          ) : line !== "realestate" ? (
            <p className="meta" style={{ marginTop: 12 }}>
              資金繰り連動の整合は不動産ラインです。
            </p>
          ) : reconcileProject ? (
            <div style={{ marginTop: 12 }}>
              <MqReconcilePanel
                year={cashflowDisplayYear}
                entity={entity}
                businessLine="realestate"
                project={reconcileProject}
                diffs={reconcileDiffs}
                factsCount={
                  filterFactsYearActual(
                    rows,
                    "realestate",
                    entity,
                    cashflowDisplayYear
                  ).length
                }
                bsAsOf={
                  pickNearestBs(
                    bsRows,
                    "realestate",
                    entity,
                    yearEndDate(cashflowDisplayYear)
                  )?.as_of_date ?? null
                }
                bsSource={
                  pickNearestBs(
                    bsRows,
                    "realestate",
                    entity,
                    yearEndDate(cashflowDisplayYear)
                  )?.source ?? null
                }
              />
            </div>
          ) : (
            <p className="meta" style={{ marginTop: 12 }}>
              投影データを作れませんでした。
            </p>
          )}
        </>
      ) : view === "trends" ? (
        <>
          <div className="card" style={{ marginTop: 12 }}>
            <header>
              <span className="lvl">条件</span>
              <strong>推移 · 自己資本</strong>
            </header>
            <div className="mq-slicer" style={{ marginTop: 10 }}>
              <div className="mq-slicer-group">
                <span className="meta">表示年度（終点）</span>
                <MqPeriodLinks
                  grain="year"
                  periods={trendYearOptions.length ? trendYearOptions : [defaultYear]}
                  current={cashflowDisplayYear}
                  makeHref={(v) =>
                    href({ a: v.slice(0, 4), grain: "year", view: "trends" })
                  }
                />
              </div>
              <div className="mq-slicer-group">
                <span className="meta">事業線</span>
                {(
                  [
                    ["realestate", "不動産"],
                    ["ai", "AI"],
                    ["all", "全体"],
                  ] as const
                ).map(([v, lab]) => (
                  <a
                    key={v}
                    className={`btn${line === v ? " primary" : ""}`}
                    href={href({ line: v, view: "trends" })}
                  >
                    {lab}
                  </a>
                ))}
              </div>
              <div className="mq-slicer-group">
                <span className="meta">主体</span>
                {(
                  [
                    ["personal", "個人"],
                    ["corporate", "法人"],
                    ["combined", "合算"],
                  ] as const
                ).map(([v, lab]) => (
                  <a
                    key={v}
                    className={`btn${entity === v ? " primary" : ""}`}
                    href={href({ entity: v, view: "trends" })}
                  >
                    {lab}
                  </a>
                ))}
              </div>
            </div>
            <p className="meta" style={{ marginTop: 8 }}>
              {lineLabel(line)} · {entityLabel(entity)} · 起点{" "}
              {equityOriginYear ?? cashflowYear}年〜{cashflowDisplayYear}年の期末
            </p>
          </div>
          <div style={{ marginTop: 12 }}>
            <MqEquityTrendPanel
              title={`${lineLabel(line)} · ${entityLabel(entity)} 自己資本推移`}
              points={equityTrendPoints}
            />
          </div>
          <MqMetricsTrendPlaceholder />
        </>
      ) : (
        <>
      <div className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">原資</span>
          <strong>投資原資メモ: {mqFundingSignal}</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          {left.title} の現金純増 {fmtMqMan(mqCashMonthly != null ? mqCashMonthly / 10_000 : null)}
          {" · "}長期借入残高 {fmtMqMan(loanTrackerLt != null ? loanTrackerLt / 10_000 : null)}
        </p>
        <p className="meta" style={{ marginTop: 6 }}>
          事業CFが薄い局面では、新規投資より空室・賃料・固定費改善が先です。
          家計側の受け止め余力は <a href="/household-bs">家計B/S</a> で確認します。
        </p>
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">スライサー</span>
          <strong>集計条件</strong>
        </header>
        <div className="mq-slicer" style={{ marginTop: 10 }}>
          <div className="mq-slicer-group">
            <span className="meta">比較</span>
            {(
              [
                ["aa", "実績 ↔ 実績"],
                ["ap", "実績 ↔ 計画"],
                ["pp", "計画 ↔ 計画"],
              ] as const
            ).map(([v, lab]) => (
              <a
                key={v}
                className={`btn${mode === v ? " primary" : ""}`}
                href={href({ mode: v })}
              >
                {lab}
              </a>
            ))}
          </div>
          <div className="mq-slicer-group">
            <span className="meta">事業線</span>
            {(
              [
                ["realestate", "不動産"],
                ["ai", "AI"],
                ["all", "全体"],
              ] as const
            ).map(([v, lab]) => (
              <a
                key={v}
                className={`btn${line === v ? " primary" : ""}`}
                href={href({ line: v })}
              >
                {lab}
              </a>
            ))}
          </div>
          <div className="mq-slicer-group">
            <span className="meta">主体</span>
            {(
              [
                ["personal", "個人"],
                ["corporate", "法人"],
                ["combined", "合算"],
              ] as const
            ).map(([v, lab]) => (
              <a
                key={v}
                className={`btn${entity === v ? " primary" : ""}`}
                href={href({ entity: v })}
              >
                {lab}
              </a>
            ))}
          </div>
          <div className="mq-slicer-group">
            <span className="meta">粒度</span>
            <a
              className={`btn${grain === "month" ? " primary" : ""}`}
              href={href({
                grain: "month",
                a: defaultMonth,
                b: months[1] || defaultMonth,
              })}
            >
              月次（参考）
            </a>
            <a
              className={`btn${grain === "year" ? " primary" : ""}`}
              href={href({
                grain: "year",
                a: defaultYear,
                b: yearsAll[1] || defaultYear,
              })}
            >
              年次
            </a>
          </div>

          {mode !== "pp" ? (
            <div className="mq-slicer-group">
              <span className="meta">{mode === "ap" ? "実績の期間" : "左（実績）"}</span>
              <MqPeriodLinks
                grain={grain}
                periods={grain === "year" ? yearsAll : months}
                current={periodA}
                makeHref={(v) => href({ a: v })}
              />
            </div>
          ) : null}
          {mode === "aa" ? (
            <div className="mq-slicer-group">
              <span className="meta">右（実績）</span>
              <MqPeriodLinks
                grain={grain}
                periods={grain === "year" ? yearsAll : months}
                current={periodB}
                makeHref={(v) => href({ b: v })}
              />
            </div>
          ) : null}

          {mode !== "aa" ? (
            <>
              <div className="mq-slicer-group">
                <span className="meta">計画の年度</span>
                <MqPeriodLinks
                  grain="year"
                  periods={yearsAll.length ? yearsAll : [defaultYear]}
                  current={planYear}
                  makeHref={(v) => href({ py: v })}
                />
              </div>
              <div className="mq-slicer-group">
                <span className="meta">{mode === "pp" ? "計画A" : "計画"}</span>
                {(variants.length ? variants : [defaultVariant]).map((v) => (
                  <a
                    key={v}
                    className={`btn${variantA === v ? " primary" : ""}`}
                    href={href({ va: v })}
                  >
                    {v}
                  </a>
                ))}
              </div>
            </>
          ) : null}
          {mode === "pp" ? (
            <div className="mq-slicer-group">
              <span className="meta">計画B</span>
              {(variants.length ? variants : [defaultVariant]).map((v) => (
                <a
                  key={`b-${v}`}
                  className={`btn${variantB === v ? " primary" : ""}`}
                  href={href({ vb: v })}
                >
                  {v}
                </a>
              ))}
            </div>
          ) : null}
        </div>
        <p className="meta" style={{ marginTop: 8 }}>
          {lineLabel(line)} · {entityLabel(entity)} ·{" "}
          {grain === "month" ? "月次（参考）表示" : "年次表示"}
          {mode === "ap" && grain === "month"
            ? " · 計画側は年額÷12で月次換算"
            : ""}
          {entity === "combined" ? " · 合算は内部取引除外推奨" : ""}
        </p>
        {grain === "year" && line === "realestate" ? (
          <p className="meta" style={{ marginTop: 6 }}>
            年次Qは `property_units` の運用戸数を使用します（現在 {annualQRealestate ?? "—"} 戸）。
            月次実績が未整備の年は、年次カテゴリ集計から暫定補完します。
          </p>
        ) : null}
      </div>

          <div className="mq-dual" style={{ marginTop: 12 }}>
            <MqStrackPanel
              title={left.title}
              computed={left.computed}
              cashBegin={cashBeginFor(periodA)}
              cashIn={
                grain === "year" && cashflowL1In != null
                  ? cashflowL1In
                  : left.cashIn
              }
              cashOut={
                grain === "year" && cashflowL1Out != null
                  ? cashflowL1Out
                  : left.cashOut
              }
              cashEnd={
                grain === "year" && cashflowL1End != null
                  ? cashflowL1End
                  : left.cashEnd
              }
              cashBridgeNote={
                grain === "year" && cashflowL1End != null
                  ? "資金繰り連動（L1 帳簿）"
                  : undefined
              }
              depreciation={left.depreciation}
              fMonthlyPart={left.fMonthlyPart ?? null}
              fAnnualAllocated={left.fAnnualAllocated ?? null}
              fBreakdownKind={left.fBreakdownKind ?? (grain === "month" ? "month" : "year")}
              includeDebtServiceInF={line === "realestate"}
              vqAccountMap={vqAccountMap}
              emptyHint={left.emptyHint}
              qUnitLabel={qLabel}
            />
            <MqStrackPanel
              title={right.title}
              computed={right.computed}
              cashBegin={mode === "aa" ? cashBeginFor(periodB) : null}
              cashIn={right.cashIn}
              cashOut={right.cashOut}
              cashEnd={right.cashEnd}
              depreciation={right.depreciation}
              fMonthlyPart={right.fMonthlyPart ?? null}
              fAnnualAllocated={right.fAnnualAllocated ?? null}
              fBreakdownKind={right.fBreakdownKind ?? (grain === "month" ? "month" : "year")}
              includeDebtServiceInF={line === "realestate"}
              vqAccountMap={vqAccountMap}
              emptyHint={right.emptyHint}
              qUnitLabel={qLabel}
            />
          </div>

          {left.fNote ? (
            <p className="meta" style={{ marginTop: 8 }}>
              {left.fNote}
            </p>
          ) : null}

          {line === "all" && byLine.length > 0 ? (
            <div className="card" style={{ marginTop: 12 }}>
              <header>
                <span className="lvl">内訳</span>
                <strong>左 · 不動産 / AI</strong>
              </header>
              <table style={{ marginTop: 8 }}>
                <thead>
                  <tr>
                    <th>事業線</th>
                    <th className="num">MQ</th>
                    <th className="num">F</th>
                    <th className="num">G</th>
                  </tr>
                </thead>
                <tbody>
                  {byLine.map((b) => (
                    <tr key={b.line}>
                      <td>{lineLabel(b.line)}</td>
                      <td className="num">{fmtMqMan(b.computed.mq)}</td>
                      <td className="num">{fmtMqMan(b.computed.f)}</td>
                      <td className="num">{fmtMqMan(b.computed.g)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          <div style={{ marginTop: 12 }}>
            <MqCompareBars
              titleA={left.title}
              titleB={right.title}
              rowsA={metricBars(left.computed)}
              rowsB={metricBars(right.computed)}
            />
          </div>

          <MqTaxComparePanel
            compare={taxCompare}
            dual={taxCompareDual}
            grain={grain}
            line={line}
            entity={entity}
            periodLabel={left.title.replace(/^実績\s*/, "")}
          />

      <div style={{ marginTop: 16 }}>
        <MqBsPanel
          title={`${lineLabel(line)} · ${entityLabel(entity)}`}
          fields={bsFields}
          mqG={left.computed?.g ?? null}
          asOfLabel={bsAsOf}
          combineNote={bsCombineNote}
          requireInventory={requireInventory}
          defaultLine={bsLine}
          defaultEntity={bsFormEntity}
          defaultAsOf={bsAsOf}
          initial={bsInitial}
          loanTrackerLt={bsLine === "realestate" ? loanTrackerLt : null}
          priorYearCash={priorYearCash}
          priorYearAsOf={priorYearAsOf}
        />
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <header>
          <span className="lvl">Zaim取込</span>
          <strong>月次実績の自動集計（Phase C）</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          承認済み科目マップで事業系だけ集計します。手入力月は既定で保護。未分類は下に出し、MQからは除外（暫定）します。
        </p>
        <div style={{ marginTop: 10 }}>
          <MqZaimIngestPanel defaultYear={planYear} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <header>
          <span className="lvl">実績入力</span>
          <strong>月次オンゴーイング</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          空室は主に Q（稼働戸月）の減少。年払いは F年額。ローン元本は出金合計（Gに入れない）。
        </p>
        <div style={{ marginTop: 10 }}>
          <MqFactsForm
            defaultLine={line === "ai" ? "ai" : "realestate"}
            defaultEntity={entity === "corporate" ? "corporate" : "personal"}
            defaultMonth={formMonth.slice(0, 7)}
          />
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <header>
          <span className="lvl">計画入力</span>
          <strong>年次パターン</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          同じ年度に「基本」「家賃+5%」など複数パターンを保存し、上の比較で差し引きできます。数値は年額。
        </p>
        <div style={{ marginTop: 10 }}>
          <MqPlanForm
            defaultLine={line === "ai" ? "ai" : "realestate"}
            defaultEntity={entity === "corporate" ? "corporate" : "personal"}
            defaultYear={planYear}
            existingVariants={variants.length ? variants : ["基本", "家賃+5%", "空室改善"]}
          />
        </div>
      </div>

      <p className="meta" style={{ marginTop: 16 }}>
        買い進め（
        <a href="/realestate/buy-plan">/realestate/buy-plan</a>
        ）は物件条件。こちらは固定費込みの粗利評価です。
      </p>
        </>
      )}
    </Shell>
  );
}
