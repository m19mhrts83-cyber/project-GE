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
  loan_match: { mini_patterns: string[]; mini_label: string };
  income_categories: string[];
};

type Snap = { as_of: string; value_jpy: number; source?: string | null };
type LiqSnap = { account_id: string; as_of: string; balance_jpy: number };
type LoanRow = {
  id: string;
  name: string | null;
  balance_jpy: number | string | null;
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
    path.join(process.cwd(), "config", "household_kiyosaki_bs.json"),
    path.join(process.cwd(), "..", "..", "config", "household_kiyosaki_bs.json"),
  ];
  for (const p of candidates) {
    try {
      if (fs.existsSync(p)) {
        return JSON.parse(fs.readFileSync(p, "utf8")) as HouseholdConfig;
      }
    } catch {
      /* try next */
    }
  }
  throw new Error("household_kiyosaki_bs.json not found");
}

function num(v: number | string | null | undefined): number {
  if (v == null || v === "") return 0;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
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
    if (!r.countsTowardTotal || r.amountJpy == null) continue;
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

  const salary = sumSalaryIncome(
    args.categoryYear ?? [],
    Number(year),
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

  const mqCombined = mqSlice(args.mqFacts, year, "combined");
  const mqPersonal = mqSlice(args.mqFacts, year, "personal");
  const mqCorporate = mqSlice(args.mqFacts, year, "corporate");

  if (mqCombined.computed && mqCombined.computed.pq !== 0) {
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

  if (mqCombined.computed) {
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
    }
  }

  for (const ln of args.loanTracker) {
    if (usedLoanIds.has(ln.id)) continue;
    const bal = num(ln.balance_jpy);
    if (bal <= 0) continue;
    const isMini = matchesMini(ln, cfg.loan_match.mini_patterns);
    const major = String(ln.category_major || "");
    if (isMini || major === "プライベート" || major === "その他") {
      rows.push({
        id: `loan_${ln.id}`,
        label: isMini ? cfg.loan_match.mini_label : ln.name || ln.id,
        quadrant: "liability",
        band: "consumer",
        amountJpy: bal,
        countsTowardTotal: true,
        source: "loan_tracker",
        hint: isMini ? "キヨサキ: CFが出ない買い物" : undefined,
      });
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

  if (grain === "year" && !mqCombined.computed) {
    notes.push(`${year}年のMQ実績がありません。/mq で取込後にフロー行が出ます。`);
  }
  if (policyLoanTotal > 0) {
    notes.push(
      "契約者貸付は次物件キープとして資産側に表示。金額は保険ネットに反映済みで合計は二重になりません。"
    );
  }

  return {
    year,
    grain,
    rows,
    totals: sumTotals(rows),
    mqSlices: [mqCombined, mqPersonal, mqCorporate],
    notes,
    composedAt: new Date().toISOString(),
  };
}

export function portfolioStyleNetJpy(view: HouseholdBsView): number {
  return view.totals.assetJpy - view.totals.liabilityJpy;
}
