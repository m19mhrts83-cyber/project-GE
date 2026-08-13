/** 資産トップ：国内株式／海外株式／海外債券の分類と投下・評価。 */

export type MixBucket = "jp_eq" | "ex_eq" | "ex_bd" | "jp_bd" | "cash" | "other";

export const MIX_LABEL: Record<MixBucket, string> = {
  jp_eq: "国内株式",
  ex_eq: "海外株式",
  ex_bd: "海外債券",
  jp_bd: "国内債券",
  cash: "現金・短期",
  other: "その他",
};

export const MIX_CORE: MixBucket[] = ["jp_eq", "ex_eq", "ex_bd"];

export type HoldingFund = {
  name?: string;
  code?: string;
  value_jpy?: number;
  pnl_jpy?: number;
  cost_unit?: number;
  units?: number;
};

export type MixSlice = {
  bucket: MixBucket;
  value: number;
  cost: number | null;
  gain: number | null;
  gainPct: number | null;
};

export function yen(n: number | string | null | undefined): number {
  const v = Number(n);
  return Number.isFinite(v) ? v : 0;
}

export function fundCost(f: HoldingFund): number | null {
  const value = yen(f.value_jpy);
  if (f.pnl_jpy != null && Number.isFinite(Number(f.pnl_jpy))) {
    return value - Number(f.pnl_jpy);
  }
  return null;
}

export function classifyHolding(name: string, code?: string): MixBucket {
  const s = `${code || ""} ${name || ""}`;
  if (/物価連動国債|国債(?!債)/.test(s) && !/外国|世界/.test(s)) return "jp_bd";
  if (/外国債|世界債券|外国債券/.test(s)) return "ex_bd";
  if (/金融市場/.test(s)) return "cash";
  if (
    /日本株|国内株式|EWJ|HEWJ|すらら|三菱重工|持株/.test(s)
  ) {
    return "jp_eq";
  }
  if (
    /先進国|新興国|S&P|ACWI|IVV|IEMG|IWB|ESGU|IXN|FXI|IEV|HEZU|EPP|世界株式|外国株|米国|ヨーロッパ|中国株式|Alphabet|Apple|Bank of America|East West|Occidental|グローバル/.test(
      s
    )
  ) {
    return "ex_eq";
  }
  if (/債券/.test(s)) return "ex_bd";
  if (/株式|株|ETF/.test(s)) return "ex_eq";
  return "other";
}

export function classifyInsuranceFund(name: string): MixBucket {
  if (/日本株式/.test(name)) return "jp_eq";
  if (/世界株式|外国株式/.test(name)) return "ex_eq";
  if (/外国債券|世界債券/.test(name)) return "ex_bd";
  if (/金融市場/.test(name)) return "cash";
  return "other";
}

const IFA_DEFAULT_FUNDS = [
  { name: "日本株式型", pct: 20 },
  { name: "世界株式プラス型", pct: 20 },
  { name: "外国債券型", pct: 20 },
  { name: "世界債券プラス型", pct: 20 },
  { name: "金融市場型", pct: 20 },
];

export function addToMix(
  acc: Record<MixBucket, MixSlice>,
  bucket: MixBucket,
  value: number,
  cost: number | null
): void {
  const row = acc[bucket];
  row.value += value;
  if (cost != null) {
    row.cost = (row.cost ?? 0) + cost;
  }
}

export function emptyMix(): Record<MixBucket, MixSlice> {
  const keys: MixBucket[] = [
    "jp_eq",
    "ex_eq",
    "ex_bd",
    "jp_bd",
    "cash",
    "other",
  ];
  const out = {} as Record<MixBucket, MixSlice>;
  for (const b of keys) {
    out[b] = { bucket: b, value: 0, cost: null, gain: null, gainPct: null };
  }
  return out;
}

export function finalizeMix(
  acc: Record<MixBucket, MixSlice>
): Record<MixBucket, MixSlice> {
  for (const row of Object.values(acc)) {
    if (row.cost != null) {
      row.gain = row.value - row.cost;
      row.gainPct = row.cost !== 0 ? row.gain / row.cost : null;
    }
  }
  return acc;
}

export function allocateInsuranceValue(
  value: number,
  funds: { name: string; pct: number }[] | undefined
): { bucket: MixBucket; value: number }[] {
  const list =
    funds && funds.length > 0
      ? funds
      : IFA_DEFAULT_FUNDS;
  const totalPct = list.reduce((s, f) => s + (f.pct || 0), 0) || 100;
  return list.map((f) => ({
    bucket: classifyInsuranceFund(f.name),
    value: value * ((f.pct || 0) / totalPct),
  }));
}

export function paidInByInsurer(
  rows: { subcategory: string | null; expense_jpy: number | string | null }[]
): Record<string, number> {
  const out: Record<string, number> = {
    axa: 0,
    sony: 0,
    prudential: 0,
  };
  for (const r of rows) {
    const sub = (r.subcategory || "").trim();
    const amt = yen(r.expense_jpy);
    if (sub.includes("アクサ")) out.axa += amt;
    else if (sub.includes("ソニー")) out.sony += amt;
    else if (sub.includes("プルデンシャル")) out.prudential += amt;
  }
  return out;
}
