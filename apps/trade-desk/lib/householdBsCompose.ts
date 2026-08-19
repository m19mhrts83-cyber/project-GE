/**
 * 家計キヨサキB/S — 既存テーブルから4象限を合成（Read Model）。
 * 正本: config/household_kiyosaki_bs.json
 */

import fs from "fs";
import path from "path";
import {
  aggregateRows,
  filterFactsYearActual,
  type MqFactRow,
} from "@/lib/mqAggregate";
import type { MqComputed } from "@/lib/mqEquations";
import { RE_PROPERTY_MASTER, loansForProperty } from "@/lib/rePropertyMaster";
import {
  buildHouseholdReFlow,
  isHouseholdReOtherIncome,
  type HouseholdReFlow,
} from "@/lib/householdReFlow";
import {
  householdFiledReFromMetrics,
  loadTaxYearMetricsFromCatalog,
  type HouseholdFiledRe,
} from "@/lib/householdReFiled";
import type { PropertyUnitRow } from "@/lib/roiAssets";
import type { TaxYearMetricRow } from "@/lib/taxInsights";

export type Quadrant = "income" | "expense" | "asset" | "liability";

export type HouseholdBsRow = {
  id: string;
  label: string;
  quadrant: Quadrant;
  band?: string;
  amountJpy: number | null;
  countsTowardTotal: boolean;
  indent?: boolean;
  asOf?: string | null;
  source?: string | null;
  hint?: string;
  entity?: "personal" | "corporate" | "combined";
  staleDays?: number | null;
};

export type MqSlice = {
  entity: "personal" | "corporate" | "combined";
  label: string;
  computed: MqComputed | null;
  pqYen: number | null;
  gYen: number | null;
};

export type HouseholdBsView = {
  year: string;
  grain: "month" | "year";
  rows: HouseholdBsRow[];
  totals: {
    incomeJpy: number;
    expenseJpy: number;
    assetJpy: number;
    liabilityJpy: number;
  };
  mqSlices: MqSlice[];
  notes: string[];
  composedAt: string;
  snapshotAsOf?: string | null;
  snapshotSource?: string | null;
  reFlow?: HouseholdReFlow | null;
  filedRe?: HouseholdFiledRe | null;
};

export type HouseholdConfig = {
  insurance_pairs: {
    gross_id: string;
    loan_id: string;
    label: string;
  }[];
  securities: {
    id: string;
    label: string;
    band: string;
    note?: string;
  }[];
  static_rows: {
    id: string;
    label: string;
    quadrant: Quadrant;
    band?: string;
    hint?: string;
  }[];
  loan_match: {
    mini_patterns: string[];
    mini_label: string;
    home_patterns?: string[];
    home_label?: string;
    exclude_patterns?: string[];
  };
  expense_flow?: { exclude_category_patterns?: string[] };
  income_categories: string[];
  realestate_flow?: {
    other_income_patterns?: string[];
    mq_in_totals?: boolean;
    income_source?: string;
  };
};

type Snap = { as_of: string; value_jpy: number; source?: string | null };
type LiqSnap = { account_id: string; as_of: string; balance_jpy: number };
type LoanRow = {
  id: string;
  name: string | null;
  balance_jpy: number | string | null;
  monthly_payment_jpy?: number | string | null;
  category_major: string | null;
  tags?: string[] | null;
  payload?: Record<string, unknown> | null;
};
type CategoryRow = {
  fiscal_year: number;
  category: string | null;
  income_jpy: number | null;
  expense_jpy: number | null;
};

export function loadHouseholdBsConfig(): HouseholdConfig {
  const candidates = [
    path.join(process.cwd(), "..", "..", "config", "household_kiyosaki_bs.yaml"),
    path.join(process.cwd(), "config", "household_kiyosaki_bs.yaml"),
    path.join(process.cwd(), "config", "household_kiyosaki_bs.json"),
    path.join(process.cwd(), "..", "..", "config", "household_kiyosaki_bs.json"),
  ];
  for (const p of candidates) {
    try {
      if (!fs.existsSync(p)) continue;
      const raw = fs.readFileSync(p, "utf8");
      if (p.endsWith(".yaml") || p.endsWith(".yml")) {
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        const { parse } = require("yaml") as typeof import("yaml");
        return parse(raw) as HouseholdConfig;
      }
      return JSON.parse(raw) as HouseholdConfig;
    } catch {
      /* try next */
    }
  }
  throw new Error("household_kiyosaki_bs config not found");
}

function staleDaysFrom(asOf: string | null | undefined): number | null {
  if (!asOf) return null;
  const d = new Date(String(asOf).slice(0, 10));
  if (Number.isNaN(d.getTime())) return null;
  const now = new Date();
  return Math.max(
    0,
    Math.floor((now.getTime() - d.getTime()) / (24 * 60 * 60 * 1000))
  );
}

function withStale<T extends HouseholdBsRow>(row: T): T {
  if (!row.asOf) return row;
  return { ...row, staleDays: staleDaysFrom(row.asOf) };
}

function num(v: number | string | null | undefined): number {
  if (v == null || v === "") return 0;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function loanAnnualPaymentJpy(loan: LoanRow): number {
  const payload = (loan.payload || {}) as {
    annualPayment?: number | string | null;
    monthlyPayment?: number | string | null;
    bonusAddAmount?: number | string | null;
    bonusMonths?: unknown;
  };
  const annual = num(payload.annualPayment);
  if (annual > 0) return annual;
  const monthly = num(payload.monthlyPayment) || num(loan.monthly_payment_jpy);
  const bonusAdd = num(payload.bonusAddAmount);
  const bonusMonths = Array.isArray(payload.bonusMonths)
    ? payload.bonusMonths.length
    : 0;
  const total = monthly * 12 + bonusAdd * bonusMonths;
  return total > 0 ? total : 0;
}

function latestSnaps(
  snaps: {
    account_id: string;
    as_of: string;
    value_jpy: number | string | null;
    source?: string | null;
  }[]
): Map<string, Snap> {
  const m = new Map<string, Snap>();
  for (const row of snaps) {
    if (row.value_jpy == null) continue;
    if (m.has(row.account_id)) continue;
    m.set(row.account_id, {
      as_of: row.as_of,
      value_jpy: num(row.value_jpy),
      source: row.source ?? null,
    });
  }
  return m;
}

function latestLiq(snaps: LiqSnap[]): Map<string, LiqSnap> {
  const m = new Map<string, LiqSnap>();
  for (const row of snaps) {
    if (m.has(row.account_id)) continue;
    m.set(row.account_id, row);
  }
  return m;
}

function mqSlice(
  rows: MqFactRow[],
  year: string,
  entity: "personal" | "corporate" | "combined"
): MqSlice {
  const subset = filterFactsYearActual(rows, "realestate", entity, year);
  const agg = aggregateRows(subset, "year");
  const c = agg.computed;
  return {
    entity,
    label:
      entity === "personal"
        ? "個人"
        : entity === "corporate"
          ? "法人"
          : "合算",
    computed: c,
    pqYen: c ? c.pq * 10_000 : null,
    gYen: c ? c.g * 10_000 : null,
  };
}

function matchesMini(loan: LoanRow, patterns: string[]): boolean {
  const blob = `${loan.name || ""} ${(loan.tags || []).join(" ")} ${loan.id}`.toUpperCase();
  return patterns.some((p) => blob.includes(p.toUpperCase()));
}

function matchesHome(loan: LoanRow, patterns: string[]): boolean {
  const payload = loan.payload as { lender?: string } | null | undefined;
  const blob = `${loan.name || ""} ${(loan.tags || []).join(" ")} ${payload?.lender || ""} ${loan.id}`.toUpperCase();
  return patterns.some((p) => blob.includes(p.toUpperCase()));
}

function matchesLoanExclude(loan: LoanRow, patterns: string[]): boolean {
  if (patterns.length === 0) return false;
  const payload = loan.payload as { lender?: string; note?: string } | null | undefined;
  const blob = `${loan.name || ""} ${(loan.tags || []).join(" ")} ${payload?.lender || ""} ${payload?.note || ""} ${loan.id}`.toUpperCase();
  return patterns.some((p) => blob.includes(p.toUpperCase()));
}

function incomeRowsFromCategories(
  cats: CategoryRow[],
  year: number,
  patterns: string[]
): HouseholdBsRow[] {
  const out: HouseholdBsRow[] = [];
  for (const r of cats) {
    if (r.fiscal_year !== year) continue;
    const cat = (r.category || "").trim();
    const inc = num(r.income_jpy);
    if (!cat || inc <= 0) continue;
    if (/19\.1/.test(cat) && /家賃|不労所得/.test(cat)) continue;
    if (!patterns.some((p) => cat.includes(p))) continue;
    const slug = cat.replace(/[^\w\u3040-\u9fff]+/g, "_").slice(0, 40);
    out.push({
      id: `zaim_income_${slug}`,
      label: cat.replace(/^[αβγδ]?\.?\d+F?\./, ""),
      quadrant: "income",
      band: "engine",
      amountJpy: inc,
      countsTowardTotal: true,
      hint: "Zaim年次",
      entity: "combined",
    });
  }
  return out;
}

function expenseRowsFromCategories(
  cats: CategoryRow[],
  year: number,
  exclude: string[]
): HouseholdBsRow[] {
  const out: HouseholdBsRow[] = [];
  for (const r of cats) {
    if (r.fiscal_year !== year) continue;
    const cat = (r.category || "").trim();
    const exp = num(r.expense_jpy);
    if (!cat || exp <= 0) continue;
    if (exclude.some((p) => cat.includes(p))) continue;
    const slug = cat.replace(/[^\w\u3040-\u9fff]+/g, "_").slice(0, 40);
    out.push({
      id: `zaim_expense_${slug}`,
      label: cat.replace(/^[αβγδ]?\.?\d+F?\./, ""),
      quadrant: "expense",
      band: "household",
      amountJpy: exp,
      countsTowardTotal: true,
      hint: "Zaim年次（家計フロー）",
      entity: "combined",
    });
  }
  return out.sort((a, b) => (b.amountJpy ?? 0) - (a.amountJpy ?? 0));
}

function sumSalaryIncome(
  cats: CategoryRow[],
  year: number,
  patterns: string[]
): number {
  let sum = 0;
  for (const r of cats) {
    if (r.fiscal_year !== year) continue;
    const cat = (r.category || "").trim();
    if (!cat) continue;
    if (!patterns.some((p) => cat.includes(p))) continue;
    sum += num(r.income_jpy);
  }
  return sum;
}

function sumTotals(rows: HouseholdBsRow[]): HouseholdBsView["totals"] {
  let incomeJpy = 0;
  let expenseJpy = 0;
  let assetJpy = 0;
  let liabilityJpy = 0;
  for (const r of rows) {
    if (r.amountJpy == null) continue;
    const includeInTotals =
      r.countsTowardTotal || (r.quadrant === "expense" && r.band === "debt_service");
    if (!includeInTotals) continue;
    const a = r.amountJpy;
    if (r.quadrant === "income") incomeJpy += a;
    else if (r.quadrant === "expense") expenseJpy += a;
    else if (r.quadrant === "asset") assetJpy += a;
    else if (r.quadrant === "liability") liabilityJpy += a;
  }
  return { incomeJpy, expenseJpy, assetJpy, liabilityJpy };
}

export function composeHouseholdBs(args: {
  year: string;
  grain?: "month" | "year";
  portfolioSnaps: {
    account_id: string;
    as_of: string;
    value_jpy: number | string;
    source?: string | null;
  }[];
  securitiesSnaps?: {
    account_id: string;
    as_of: string;
    value_jpy: number | string | null;
    source?: string | null;
  }[];
  liquiditySnaps: LiqSnap[];
  liquidityLabels?: Map<string, string>;
  mqFacts: MqFactRow[];
  loanTracker: LoanRow[];
  categoryYear?: CategoryRow[];
  propertyUnits?: PropertyUnitRow[];
  taxMetrics?: TaxYearMetricRow[];
  cardDebitAmountJpy?: number | null;
  cardDebitDue?: string | null;
  config?: HouseholdConfig;
}): HouseholdBsView {
  const cfg = args.config ?? loadHouseholdBsConfig();
  const year = args.year.slice(0, 4);
  const grain = args.grain ?? "year";
  const rows: HouseholdBsRow[] = [];
  const notes: string[] = [];
  const pf = latestSnaps(args.portfolioSnaps);
  const sec = latestSnaps(args.securitiesSnaps ?? []);
  const yNum = Number(year);

  const incomeFromZaim = incomeRowsFromCategories(
    args.categoryYear ?? [],
    yNum,
    cfg.income_categories
  );
  if (incomeFromZaim.length > 0) {
    rows.push(...incomeFromZaim);
  } else {
    const salary = sumSalaryIncome(
      args.categoryYear ?? [],
      yNum,
      cfg.income_categories
    );
    if (salary > 0) {
      rows.push({
        id: "salary",
        label: "給与・賞与",
        quadrant: "income",
        band: "engine",
        amountJpy: salary,
        countsTowardTotal: true,
        hint: "Zaim年次。エンジンであり資産ではない",
        entity: "combined",
      });
    }
  }

  const mqCombined = mqSlice(args.mqFacts, year, "combined");
  const mqPersonal = mqSlice(args.mqFacts, year, "personal");
  const mqCorporate = mqSlice(args.mqFacts, year, "corporate");
  const mqInTotals = cfg.realestate_flow?.mq_in_totals === true;
  const taxMetrics = args.taxMetrics ?? loadTaxYearMetricsFromCatalog();
  const filedRe = householdFiledReFromMetrics(taxMetrics, yNum);
  const occupancyInTotals = !filedRe.useFiledInTotals;

  const reFlow = buildHouseholdReFlow({
    year: yNum,
    units: args.propertyUnits ?? [],
  });

  if (filedRe.useFiledInTotals && filedRe.personalRevenueJpy) {
    rows.push({
      id: "re_rent_filed_personal",
      label: "不動産家賃（確定申告・個人）",
      quadrant: "income",
      band: "business_cf",
      amountJpy: filedRe.personalRevenueJpy,
      countsTowardTotal: true,
      hint: "収支内訳書の収入金額。提出PDFが正",
      source: filedRe.personalSource ?? "tax_return",
      entity: "personal",
    });
  }
  if (filedRe.useFiledInTotals && filedRe.corporateRevenueJpy) {
    rows.push({
      id: "re_rent_filed_corporate",
      label: "不動産売上（確定申告・法人5月期）",
      quadrant: "income",
      band: "business_cf",
      amountJpy: filedRe.corporateRevenueJpy,
      countsTowardTotal: true,
      hint: "法人申告の売上。暦年とは期間がずれる",
      source: filedRe.corporateSource ?? "tax_return",
      entity: "corporate",
    });
  }

  if (reFlow.totals.grossJpy > 0) {
    rows.push({
      id: "re_rent_gross",
      label: occupancyInTotals
        ? "不動産家賃（内容確認・グロス）"
        : "　↳ 内容確認（参考・合計には含めない）",
      quadrant: "income",
      band: "business_cf",
      amountJpy: reFlow.totals.grossJpy,
      countsTowardTotal: occupancyInTotals,
      indent: !occupancyInTotals,
      hint: occupancyInTotals
        ? reFlow.basis
        : "申告後は内容確認を参考表示のみ。当年空室は未反映",
      source: "occupancy",
      asOf: reFlow.asOf,
      entity: "combined",
    });
    for (const p of reFlow.properties) {
      rows.push({
        id: `re_rent_${p.id}`,
        label: `　↳ ${p.label}（${p.owner}・${p.months}ヶ月）`,
        quadrant: "income",
        band: "business_cf",
        amountJpy: p.grossJpy,
        countsTowardTotal: false,
        indent: true,
        hint: `家賃 ${p.rentJpy.toLocaleString("ja-JP")} + 管理費 ${p.mgmtJpy.toLocaleString("ja-JP")}`,
        source: "occupancy",
        entity: p.owner === "法人" ? "corporate" : "personal",
      });
    }
    if (occupancyInTotals && reFlow.totals.mgmtJpy > 0) {
      rows.push({
        id: "re_mgmt_expense",
        label: "不動産管理費（内容確認）",
        quadrant: "expense",
        band: "business_cf",
        amountJpy: reFlow.totals.mgmtJpy,
        countsTowardTotal: true,
        hint: "未申告年。財務19.1は管理費差引後のため、グロスから管理費を支出へ戻す",
        source: "occupancy",
        asOf: reFlow.asOf,
        entity: "combined",
      });
      for (const p of reFlow.properties) {
        if (p.mgmtJpy <= 0) continue;
        rows.push({
          id: `re_mgmt_${p.id}`,
          label: `　↳ ${p.label}`,
          quadrant: "expense",
          band: "business_cf",
          amountJpy: p.mgmtJpy,
          countsTowardTotal: false,
          indent: true,
          source: "occupancy",
        });
      }
    }
  } else if (!filedRe.useFiledInTotals) {
    notes.push(
      "不動産家賃は内容確認（property_units）が空のため未計上。③-Cの号室を確認してください。"
    );
  }

  for (const r of args.categoryYear ?? []) {
    if (r.fiscal_year !== yNum) continue;
    const cat = (r.category || "").trim();
    const inc = num(r.income_jpy);
    if (inc <= 0 || !isHouseholdReOtherIncome(cat)) continue;
    const slug = cat.replace(/[^\w\u3040-\u9fff]+/g, "_").slice(0, 40);
    rows.push({
      id: `zaim_re_other_${slug}`,
      label: cat.replace(/^[αβγδ]?\.?\d+F?\./, ""),
      quadrant: "income",
      band: "business_cf",
      amountJpy: inc,
      countsTowardTotal: true,
      hint: "財務年次の不動産その他（売却・保険金・事業収入）。19.1家賃は使わない",
      source: "finance_year",
      entity: "combined",
    });
  }

  if (mqInTotals && mqCombined.computed && mqCombined.computed.pq !== 0) {
    rows.push({
      id: "mq_rent_pq",
      label: "不動産売上（MQ・PQ合算）",
      quadrant: "income",
      band: "business_cf",
      amountJpy: mqCombined.pqYen,
      countsTowardTotal: true,
      hint: "事業CF。個人+法人合算",
      entity: "combined",
    });
  }

  if (mqInTotals && mqCombined.computed) {
    const expMan = (mqCombined.computed.vq || 0) + (mqCombined.computed.f || 0);
    if (expMan !== 0) {
      rows.push({
        id: "mq_re_expense",
        label: "不動産経費（MQ・VQ+F合算）",
        quadrant: "expense",
        band: "business_cf",
        amountJpy: expMan * 10_000,
        countsTowardTotal: true,
        hint: "現金ベース事業費。元本返済は含まない",
        entity: "combined",
      });
    }
  }

  const zaimExpenses = expenseRowsFromCategories(
    args.categoryYear ?? [],
    yNum,
    cfg.expense_flow?.exclude_category_patterns ?? [
      "MQ",
      "不動産",
      "合計",
      "19",
      "賃貸",
      "マンション",
    ]
  );
  rows.push(...zaimExpenses);

  let homeLoanFilled = false;
  for (const s of cfg.static_rows) {
    rows.push({
      id: s.id,
      label: s.label,
      quadrant: s.quadrant,
      band: s.band,
      amountJpy: null,
      countsTowardTotal: false,
      hint: s.hint,
    });
  }

  let policyLoanTotal = 0;
  for (const pair of cfg.insurance_pairs) {
    const gross = pf.get(pair.gross_id);
    const loan = pf.get(pair.loan_id);
    const grossVal = gross?.value_jpy ?? 0;
    const loanVal = loan?.value_jpy ?? 0;
    policyLoanTotal += loanVal;
    const net = grossVal - loanVal;
    if (gross || loan) {
      rows.push({
        id: `ins_net_${pair.gross_id}`,
        label: pair.label,
        quadrant: "asset",
        band: "insurance_net",
        amountJpy:
          grossVal === 0 && loanVal === 0
            ? null
            : net,
        countsTowardTotal: true,
        asOf: gross?.as_of ?? loan?.as_of ?? null,
        source: gross?.source ?? loan?.source ?? "portfolio",
      });
      if (loanVal > 0 && loan) {
        rows.push({
          id: `policy_loan_${pair.loan_id}`,
          label: "　↳ うち借入（次物件キープ）",
          quadrant: "asset",
          band: "next_property",
          amountJpy: loanVal,
          countsTowardTotal: false,
          indent: true,
          asOf: loan.as_of,
          source: loan.source ?? "portfolio",
          hint: "保険ネットに含む。合計には再加算しない",
        });
      }
    }
  }

  for (const secDef of cfg.securities) {
    const h = sec.get(secDef.id) ?? pf.get(secDef.id);
    if (!h || h.value_jpy === 0) continue;
    rows.push({
      id: secDef.id,
      label: secDef.label,
      quadrant: "asset",
      band: secDef.band,
      amountJpy: h.value_jpy,
      countsTowardTotal: true,
      asOf: h.as_of,
      source: h.source ?? "securities",
      hint: secDef.note,
    });
  }

  const liqLatest = latestLiq(args.liquiditySnaps);
  for (const [id, snap] of liqLatest) {
    const name = args.liquidityLabels?.get(id) ?? id;
    rows.push({
      id: `liq_${id}`,
      label: name,
      quadrant: "asset",
      band: "cash",
      amountJpy: num(snap.balance_jpy),
      countsTowardTotal: true,
      asOf: snap.as_of,
      source: "liquidity",
    });
  }

  const usedLoanIds = new Set<string>();
  for (const prop of RE_PROPERTY_MASTER) {
    const propLoans = loansForProperty(prop.id, args.loanTracker);
    rows.push({
      id: `re_asset_${prop.id}`,
      label: `${prop.name}（${prop.owner}）`,
      quadrant: "asset",
      band: "business_cf",
      amountJpy: null,
      countsTowardTotal: false,
      hint: "評価額は③-C/MQ参照。ここは事業CFの枠",
      entity: prop.owner === "法人" ? "corporate" : "personal",
    });
    for (const ln of propLoans) {
      usedLoanIds.add(ln.id);
      const bal = num(ln.balance_jpy);
      if (bal <= 0) continue;
      rows.push({
        id: `re_loan_${ln.id}`,
        label: `　↳ ${ln.name || ln.id}`,
        quadrant: "asset",
        band: "good_debt",
        amountJpy: bal,
        countsTowardTotal: false,
        indent: true,
        hint: "良い借金",
        entity: prop.owner === "法人" ? "corporate" : "personal",
      });
      rows.push({
        id: `re_loan_liab_${ln.id}`,
        label: ln.name || ln.id,
        quadrant: "liability",
        band: "good_debt",
        amountJpy: bal,
        countsTowardTotal: true,
        source: "loan_tracker",
      });
      const annualPay = loanAnnualPaymentJpy(ln);
      if (annualPay > 0) {
        rows.push({
          id: `re_loan_pay_${ln.id}`,
          label: `　↳ 年返済 ${ln.name || ln.id}`,
          quadrant: "expense",
          band: "debt_service",
          amountJpy: annualPay,
          countsTowardTotal: false,
          indent: true,
          hint: "元本を含む返済。Cash is King 用のキャッシュ流出",
          source: "loan_tracker",
          entity: prop.owner === "法人" ? "corporate" : "personal",
        });
      }
    }
  }

  for (const ln of args.loanTracker) {
    if (usedLoanIds.has(ln.id)) continue;
    const excludePatterns = cfg.loan_match.exclude_patterns ?? [];
    if (matchesLoanExclude(ln, excludePatterns)) continue;
    const bal = num(ln.balance_jpy);
    if (bal <= 0) continue;
    const homePatterns = cfg.loan_match.home_patterns ?? [];
    const isHome =
      homePatterns.length > 0 && matchesHome(ln, homePatterns);
    const isMini = matchesMini(ln, cfg.loan_match.mini_patterns);
    const major = String(ln.category_major || "");
    if (isHome) {
      const annualPay = loanAnnualPaymentJpy(ln);
      rows.push({
        id: `loan_${ln.id}`,
        label: cfg.loan_match.home_label || ln.name || ln.id,
        quadrant: "liability",
        band: "consumer",
        amountJpy: bal,
        countsTowardTotal: true,
        source: "loan_tracker",
        hint: "自宅ローン。loan-tracker 残高",
        asOf: (ln.payload as { asOf?: string } | null)?.asOf ?? null,
      });
      if (annualPay > 0) {
        rows.push({
          id: `loan_pay_${ln.id}`,
          label: "住宅ローン返済（年・キャッシュ）",
          quadrant: "expense",
          band: "debt_service",
          amountJpy: annualPay,
          countsTowardTotal: false,
          hint: "元本を含む返済。会計費用ではなくキャッシュ流出として扱う",
          source: "loan_tracker",
        });
      }
      homeLoanFilled = true;
      usedLoanIds.add(ln.id);
      continue;
    }
    if (isMini || major === "プライベート" || major === "その他") {
      const annualPay = loanAnnualPaymentJpy(ln);
      rows.push({
        id: `loan_${ln.id}`,
        label: isMini ? cfg.loan_match.mini_label : ln.name || ln.id,
        quadrant: "liability",
        band: "consumer",
        amountJpy: bal,
        countsTowardTotal: true,
        source: "loan_tracker",
        hint: isMini ? "キヨサキ: CFが出ない買い物" : undefined,
        asOf: (ln.payload as { asOf?: string } | null)?.asOf ?? null,
      });
      if (annualPay > 0) {
        rows.push({
          id: `loan_pay_${ln.id}`,
          label: `返済（年・キャッシュ）${isMini ? cfg.loan_match.mini_label : ln.name || ln.id}`,
          quadrant: "expense",
          band: "debt_service",
          amountJpy: annualPay,
          countsTowardTotal: false,
          hint: "元本を含む返済。Cash is King 用のキャッシュ流出",
          source: "loan_tracker",
        });
      }
      usedLoanIds.add(ln.id);
    }
  }

  if (args.cardDebitAmountJpy != null && args.cardDebitAmountJpy > 0) {
    rows.push({
      id: "card_debit_pending",
      label: "クレカ引落予定",
      quadrant: "liability",
      band: "bridge",
      amountJpy: args.cardDebitAmountJpy,
      countsTowardTotal: true,
      hint: args.cardDebitDue ? `引落日 ${args.cardDebitDue}` : "card_debit_watch",
    });
  }

  notes.push(
    filedRe.useFiledInTotals
      ? "過去年の家賃収入は確定申告（収支内訳の収入金額）が正。内容確認は参考。準拠: docs/KURASHIFT_家計BS_不動産フロー.md"
      : "未申告年の家賃は内容確認（property_units）×所有月。申告後にPDFを正へ差し替える。準拠: docs/KURASHIFT_家計BS_不動産フロー.md"
  );
  if (!mqInTotals) {
    notes.push("MQのPQ・経費は家計B/S合計に入れていません（参考カードのみ）。");
  }
  if (grain === "year" && !mqCombined.computed) {
    notes.push(`${year}年のMQ実績はありません。事業側は /mq を参照。`);
  }
  if (!homeLoanFilled) {
    notes.push(
      "自宅ローン（大垣共立）は loan-tracker に未登録です。残高が分かればトラッカーへ追加してください。"
    );
  }
  if (policyLoanTotal > 0) {
    notes.push(
      "契約者貸付は次物件キープとして資産側に表示。金額は保険ネットに反映済みで合計は二重になりません。"
    );
  }
  notes.push(
    "ローン返済は、会計上の支出合計には入れず、Cash is King 用のキャッシュ支出として別表示します。"
  );

  return {
    year,
    grain,
    rows: rows.map(withStale),
    totals: sumTotals(rows),
    mqSlices: [mqCombined, mqPersonal, mqCorporate],
    notes,
    composedAt: new Date().toISOString(),
    reFlow,
    filedRe,
  };
}

/** DB スナップ payload → View（Phase C） */
export function householdBsViewFromSnapshot(payload: unknown): HouseholdBsView | null {
  if (!payload || typeof payload !== "object") return null;
  const p = payload as Partial<HouseholdBsView>;
  if (!Array.isArray(p.rows) || !p.totals || !p.year) return null;
  return {
    year: String(p.year),
    grain: p.grain === "month" ? "month" : "year",
    rows: p.rows as HouseholdBsRow[],
    totals: p.totals as HouseholdBsView["totals"],
    mqSlices: (p.mqSlices as MqSlice[]) ?? [],
    notes: (p.notes as string[]) ?? [],
    composedAt: String(p.composedAt ?? new Date().toISOString()),
    snapshotAsOf: p.snapshotAsOf ?? null,
    snapshotSource: p.snapshotSource ?? null,
    reFlow: (p.reFlow as HouseholdReFlow | undefined) ?? null,
    filedRe: (p.filedRe as HouseholdFiledRe | undefined) ?? null,
  };
}

export function portfolioStyleNetJpy(view: HouseholdBsView): number {
  return view.totals.assetJpy - view.totals.liabilityJpy;
}
