/** αβγ 分類。`scripts/jarvis_kurashift_lifeplan.py` の classify_abg と揃える。 */

export type AbgBucket =
  | "alpha"
  | "beta"
  | "gamma"
  | "delta_re"
  | "income"
  | "other";

export type CostNature = "fixed" | "variable" | "spot" | "other";

export type Mark = "○" | "△" | "×";

export const ABG_MEANING = [
  {
    key: "alpha" as const,
    glyph: "α",
    title: "貯蓄・投資",
    blurb: "積立や投資など、将来に残すお金",
    targetPct: 20,
  },
  {
    key: "beta" as const,
    glyph: "β",
    title: "生活",
    blurb: "食・住・保険・クルマなど、暮らしの経費",
    targetPct: 60,
  },
  {
    key: "gamma" as const,
    glyph: "γ",
    title: "自己・教育",
    blurb: "学びと子ども教育など、人への投資",
    targetPct: 20,
  },
] as const;

export const NATURE_MEANING = [
  {
    key: "fixed" as const,
    code: "F",
    title: "固定",
    blurb: "Zaim の F。住居・保険・学費など、毎月ほぼ決まって出る",
  },
  {
    key: "variable" as const,
    code: "C",
    title: "変動",
    blurb: "Zaim の C。食費・交際・日用品など、使い方で増減する",
  },
  {
    key: "spot" as const,
    code: "S",
    title: "スポット",
    blurb: "Zaim の S。帰省・大型出費・ご褒美など、たまに乗る",
  },
] as const;

/**
 * 固定→変動の識別。αβγの「目標差の ○△×」とは別。
 * ×（変更しない）→ △（固定でも見直し余地）→ ○（予算で削れる）
 */
export const CONTROL_MEANING = [
  {
    mark: "×" as const,
    title: "変更困難（しない）",
    blurb: "固定的で、今は手を付けない。住宅ローン・学費・奨学金・積立など",
  },
  {
    mark: "△" as const,
    title: "固定費削減検討の価値あり",
    blurb: "固定費のうち、まだ見直せる余地がある。保険・クルマ維持・インフラなど",
  },
  {
    mark: "○" as const,
    title: "予算見て削減可能",
    blurb: "変動的で、統制可能。食費・交際・帰省・ご褒美など",
  },
] as const;

/** × 変更困難。F のうち契約・返済で止めないもの */
const CONTROL_HARD_FIXED = [
  "1F.住まい",
  "10.2F",
  "10.3F",
  "15F",
  "奨学金",
];

/** △ 固定だが見直し余地。残り F は原則こちら（HARD 以外） */
const CONTROL_REVIEW_FIXED = [
  "11.1F",
  "11.2F",
  "13.1F",
  "13.2F",
  "21F",
  "生命保険",
  "自動車保険",
  "クルマ維持",
  "生活インフラ",
  "AIリスキリング",
];

export type FinanceCategoryYearRow = {
  fiscal_year: number;
  category: string | null;
  income_jpy: number | null;
  expense_jpy: number | null;
};

export type AbgYear = {
  year: number;
  periodLabel: string;
  incomeHousehold: number;
  spendTotal: number;
  alpha: number;
  beta: number;
  gamma: number;
  deltaRe: number;
  alphaPct: number | null;
  betaPct: number | null;
  gammaPct: number | null;
  fixed: number;
  variable: number;
  spot: number;
  fixedPct: number | null;
  variablePct: number | null;
  spotPct: number | null;
  controlHard: number;
  controlReview: number;
  controlFlex: number;
  controlHardPct: number | null;
  controlReviewPct: number | null;
  controlFlexPct: number | null;
};

export function classifyAbg(category: string): AbgBucket {
  const c = (category || "").trim();
  if (!c || c === "合計") return "other";
  if (c.startsWith("α") || c.slice(0, 4).includes("α.")) return "alpha";
  if (c.startsWith("β") || c.slice(0, 4).includes("β.")) return "beta";
  if (c.startsWith("γ") || c.slice(0, 4).includes("γ.")) return "gamma";
  if (c.startsWith("δ") || c.startsWith("19") || c.slice(0, 4).includes("19")) {
    return "delta_re";
  }
  if (/^0\./.test(c)) return "income";
  if (c.startsWith("19") || c.includes("不動産") || c.includes("賃貸") || c.includes("不労所得")) {
    return "delta_re";
  }
  // 「自己投資」も「投資」を含むため、γ より先に α になる（Python と同じ）
  if (c.startsWith("B.") || c.includes("投資")) return "alpha";
  if (
    [
      "6.2",
      "自己投資",
      "10.2",
      "こども教育",
      "こども学費",
      "21F",
      "AIリスキリング",
      "10.3",
      "学資",
    ].some((x) => c.includes(x))
  ) {
    return "gamma";
  }
  if (c.startsWith("A.") || c.includes("会社費用")) return "other";
  if (
    c.startsWith("G.") ||
    c.startsWith("H.") ||
    c.startsWith("J.") ||
    c.includes("借換") ||
    c.includes("株売却")
  ) {
    return "other";
  }
  if (/^(?:\d|1[0-7]|20)/.test(c) || /住まい|食費|水道|通信|医療|交通|保険|帰省/.test(c)) {
    return "beta";
  }
  return "other";
}

/** Zaim 費目コード: F=固定 / C=変動 / S=スポット */
export function classifyNature(category: string): CostNature {
  const c = (category || "").trim();
  if (/\dS\.|[.]S[.]/.test(c)) return "spot";
  if (/\dF\.|[.]F[.]/.test(c)) return "fixed";
  if (/\dC\.|[.]C[.]/.test(c) || /C\s/.test(c)) return "variable";
  return "other";
}

/**
 * 変えにくさ。C/S → ○。F は HARD=×、REVIEW=△、未列挙の F は ×。
 */
export function classifyControl(category: string): Mark | null {
  const c = (category || "").trim();
  // 積立・投資は変動コードでも「削らない」
  if (c.includes("B.C") || (c.includes("投資") && !c.includes("自己投資"))) {
    return "×";
  }
  const nature = classifyNature(c);
  if (nature === "variable" || nature === "spot") return "○";
  if (nature !== "fixed") return null;
  if (CONTROL_HARD_FIXED.some((x) => c.includes(x))) return "×";
  if (CONTROL_REVIEW_FIXED.some((x) => c.includes(x))) return "△";
  return "×";
}

export function pctOf(amount: number, denom: number): number | null {
  if (!denom) return null;
  return Math.round((1000 * amount) / denom) / 10;
}

/** 目標との差。±3pt 以内○、±8pt 以内△、それ以外× */
export function markVsTarget(
  pct: number | null | undefined,
  target: number
): Mark | null {
  if (pct == null) return null;
  const d = Math.abs(pct - target);
  if (d <= 3) return "○";
  if (d <= 8) return "△";
  return "×";
}

/** 前年比。上がると困るもの（固定・スポット）は増加で厳しく見る。 */
export function markVsPrev(
  prevPct: number | null | undefined,
  nowPct: number | null | undefined,
  risingIsBad: boolean
): Mark | null {
  if (prevPct == null || nowPct == null) return null;
  const d = nowPct - prevPct;
  if (risingIsBad) {
    if (d <= 2) return "○";
    if (d <= 5) return "△";
    return "×";
  }
  const ad = Math.abs(d);
  if (ad <= 3) return "○";
  if (ad <= 8) return "△";
  return "×";
}

function emptyYear(year: number, periodLabel: string): AbgYear {
  return {
    year,
    periodLabel,
    incomeHousehold: 0,
    spendTotal: 0,
    alpha: 0,
    beta: 0,
    gamma: 0,
    deltaRe: 0,
    alphaPct: null,
    betaPct: null,
    gammaPct: null,
    fixed: 0,
    variable: 0,
    spot: 0,
    fixedPct: null,
    variablePct: null,
    spotPct: null,
    controlHard: 0,
    controlReview: 0,
    controlFlex: 0,
    controlHardPct: null,
    controlReviewPct: null,
    controlFlexPct: null,
  };
}

export function aggregateAbgFromCategoryYear(
  rows: FinanceCategoryYearRow[],
  year: number,
  periodLabel: string
): AbgYear {
  const out = emptyYear(year, periodLabel);
  for (const r of rows) {
    if (r.fiscal_year !== year) continue;
    const cat = (r.category || "").trim();
    if (!cat || cat === "合計") continue;
    const bucket = classifyAbg(cat);
    const inc = Number(r.income_jpy) || 0;
    const exp = Number(r.expense_jpy) || 0;
    if (bucket === "income") {
      out.incomeHousehold += inc;
      continue;
    }
    if (bucket === "delta_re") {
      out.deltaRe += exp;
      continue;
    }
    if (bucket !== "alpha" && bucket !== "beta" && bucket !== "gamma") continue;
    if (bucket === "alpha") out.alpha += exp;
    else if (bucket === "beta") out.beta += exp;
    else out.gamma += exp;
    const nature = classifyNature(cat);
    if (nature === "fixed") out.fixed += exp;
    else if (nature === "variable") out.variable += exp;
    else if (nature === "spot") out.spot += exp;
    const control = classifyControl(cat);
    if (control === "×") out.controlHard += exp;
    else if (control === "△") out.controlReview += exp;
    else if (control === "○") out.controlFlex += exp;
  }
  out.spendTotal = out.alpha + out.beta + out.gamma;
  out.alphaPct = pctOf(out.alpha, out.spendTotal);
  out.betaPct = pctOf(out.beta, out.spendTotal);
  out.gammaPct = pctOf(out.gamma, out.spendTotal);
  out.fixedPct = pctOf(out.fixed, out.spendTotal);
  out.variablePct = pctOf(out.variable, out.spendTotal);
  out.spotPct = pctOf(out.spot, out.spendTotal);
  out.controlHardPct = pctOf(out.controlHard, out.spendTotal);
  out.controlReviewPct = pctOf(out.controlReview, out.spendTotal);
  out.controlFlexPct = pctOf(out.controlFlex, out.spendTotal);
  return out;
}

export function abgYearFromSnapshot(
  year: number,
  periodLabel: string,
  m: {
    income_household_jpy?: number | null;
    expense_alpha_jpy?: number | null;
    expense_beta_jpy?: number | null;
    expense_gamma_jpy?: number | null;
    expense_delta_re_jpy?: number | null;
  } | null
): AbgYear | null {
  if (!m) return null;
  const alpha = Number(m.expense_alpha_jpy) || 0;
  const beta = Number(m.expense_beta_jpy) || 0;
  const gamma = Number(m.expense_gamma_jpy) || 0;
  const spendTotal = alpha + beta + gamma;
  const incomeHousehold = Number(m.income_household_jpy) || 0;
  if (!spendTotal && !incomeHousehold) return null;
  return {
    ...emptyYear(year, periodLabel),
    incomeHousehold,
    spendTotal,
    alpha,
    beta,
    gamma,
    deltaRe: Number(m.expense_delta_re_jpy) || 0,
    alphaPct: pctOf(alpha, spendTotal),
    betaPct: pctOf(beta, spendTotal),
    gammaPct: pctOf(gamma, spendTotal),
  };
}
