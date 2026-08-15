/**
 * MQ会計評価 — 軽量B/S（第5表要約）
 * NULL は未入力。合計計算で 0 扱いしても「完成」にはしない。
 */

export type MqBsFields = {
  cash: number | null;
  receivables: number | null;
  inventory: number | null;
  fixed_assets: number | null;
  liabilities_st: number | null;
  liabilities_lt: number | null;
  capital: number | null;
  retained_earnings: number | null;
  current_profit: number | null;
};

export type MqBsRow = MqBsFields & {
  id?: string;
  business_line: string;
  entity: string;
  as_of_date: string;
  note?: string | null;
  source?: string;
};

export const BS_ASSET_KEYS = [
  "cash",
  "receivables",
  "inventory",
  "fixed_assets",
] as const;

export const BS_LIAB_EQ_KEYS = [
  "liabilities_st",
  "liabilities_lt",
  "capital",
  "retained_earnings",
  "current_profit",
] as const;

export const BS_FIELD_LABELS: Record<keyof MqBsFields, string> = {
  cash: "現金・預金",
  receivables: "売掛・未収",
  inventory: "棚卸資産",
  fixed_assets: "固定資産",
  liabilities_st: "短期他人資本",
  liabilities_lt: "長期他人資本",
  capital: "資本金等",
  retained_earnings: "繰越利益",
  current_profit: "当期利益",
};

function nNull(v: number | string | null | undefined): number | null {
  if (v == null || v === "") return null;
  const x = Number(v);
  return Number.isFinite(x) ? x : null;
}

/** 合計用: null は 0 として足すが、complete 判定とは別 */
function n0(v: number | null): number {
  return v ?? 0;
}

export function normalizeBs(raw: Partial<MqBsFields>): MqBsFields {
  return {
    cash: nNull(raw.cash as number | string | null),
    receivables: nNull(raw.receivables as number | string | null),
    inventory: nNull(raw.inventory as number | string | null),
    fixed_assets: nNull(raw.fixed_assets as number | string | null),
    liabilities_st: nNull(raw.liabilities_st as number | string | null),
    liabilities_lt: nNull(raw.liabilities_lt as number | string | null),
    capital: nNull(raw.capital as number | string | null),
    retained_earnings: nNull(raw.retained_earnings as number | string | null),
    current_profit: nNull(raw.current_profit as number | string | null),
  };
}

export function sumAssets(b: MqBsFields): number {
  return (
    n0(b.cash) +
    n0(b.receivables) +
    n0(b.inventory) +
    n0(b.fixed_assets)
  );
}

export function sumLiabEquity(b: MqBsFields): number {
  return (
    n0(b.liabilities_st) +
    n0(b.liabilities_lt) +
    n0(b.capital) +
    n0(b.retained_earnings) +
    n0(b.current_profit)
  );
}

/** 賃貸向け: 棚卸は必須にしない */
export function missingBsFields(
  b: MqBsFields,
  opts?: { requireInventory?: boolean }
): (keyof MqBsFields)[] {
  const requireInventory = opts?.requireInventory ?? false;
  const keys: (keyof MqBsFields)[] = [
    "cash",
    "receivables",
    "fixed_assets",
    "liabilities_st",
    "liabilities_lt",
    "capital",
    "retained_earnings",
    "current_profit",
  ];
  if (requireInventory) keys.splice(2, 0, "inventory");
  return keys.filter((k) => b[k] == null);
}

export function isBsComplete(
  b: MqBsFields,
  opts?: { requireInventory?: boolean }
): boolean {
  return missingBsFields(b, opts).length === 0;
}

/**
 * 貸借一致。未入力があるときは false（ゼロ埋め一致を「OK」にしない）
 */
export function isBsBalanced(
  b: MqBsFields,
  opts?: { requireInventory?: boolean; tolerance?: number }
): boolean {
  if (!isBsComplete(b, opts)) return false;
  const tol = opts?.tolerance ?? 1;
  return Math.abs(sumAssets(b) - sumLiabEquity(b)) <= tol;
}

/**
 * 個人+法人の合算。
 * - 片方のみ → その側を返す（呼び出し側で「合算不完全」注記）
 * - 両方あり・項目が片方だけ null → その項目は null（0捏造しない）
 * - 両方数値 → 加算
 */
export function combineBs(
  a: MqBsFields | null,
  b: MqBsFields | null
): MqBsFields | null {
  if (!a && !b) return null;
  if (a && !b) return { ...a };
  if (!a && b) return { ...b };
  const keys = Object.keys(BS_FIELD_LABELS) as (keyof MqBsFields)[];
  const out = emptyBs();
  for (const k of keys) {
    const va = a![k];
    const vb = b![k];
    if (va == null && vb == null) out[k] = null;
    else if (va == null || vb == null) out[k] = null;
    else out[k] = va + vb;
  }
  return out;
}

export function emptyBs(): MqBsFields {
  return {
    cash: null,
    receivables: null,
    inventory: null,
    fixed_assets: null,
    liabilities_st: null,
    liabilities_lt: null,
    capital: null,
    retained_earnings: null,
    current_profit: null,
  };
}

/**
 * 表示用の当期利益: DB値があれば優先。なければ MQ の G を参考（保存しない）
 */
export function resolveCurrentProfit(
  b: MqBsFields,
  mqG: number | null | undefined
): { value: number | null; fromMq: boolean } {
  if (b.current_profit != null) {
    return { value: b.current_profit, fromMq: false };
  }
  if (mqG != null && Number.isFinite(mqG)) {
    return { value: mqG, fromMq: true };
  }
  return { value: null, fromMq: false };
}

/** as_of 候補: YYYY-MM → 月末日（簡易） */
export function monthEndDate(ym: string): string {
  const m = ym.slice(0, 7);
  const [y, mo] = m.split("-").map(Number);
  const last = new Date(y, mo, 0).getDate();
  return `${m}-${String(last).padStart(2, "0")}`;
}

export function pickNearestBs(
  rows: MqBsRow[],
  line: string,
  entity: string,
  asOf: string
): MqBsRow | null {
  const d = asOf.slice(0, 10);
  const candidates = rows
    .filter(
      (r) =>
        r.business_line === line &&
        r.entity === entity &&
        String(r.as_of_date).slice(0, 10) <= d
    )
    .sort((a, b) =>
      String(b.as_of_date).localeCompare(String(a.as_of_date))
    );
  return candidates[0] ?? null;
}

export function yearEndDate(year: string): string {
  return `${year.slice(0, 4)}-12-31`;
}
