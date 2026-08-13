/**
 * 買い進め Excel の action 生値 → 表示用ラベル／種別。
 * KPI 集計・年表色分けで共用。
 */

export type BuyPlanActionKind =
  | "purchase"
  | "sale"
  | "finance"
  | "refinance"
  | "other";

export type BuyPlanActionView = {
  kind: BuyPlanActionKind;
  label: string;
  /** バッジ背景 */
  bg: string;
  /** バッジ文字色 */
  fg: string;
};

const KIND_STYLE: Record<
  BuyPlanActionKind,
  { bg: string; fg: string; fallback: string }
> = {
  purchase: { bg: "#e8f5e9", fg: "#1b5e20", fallback: "購入" },
  sale: { bg: "#fff3e0", fg: "#e65100", fallback: "売却" },
  finance: { bg: "#e3f2fd", fg: "#0d47a1", fallback: "調達" },
  refinance: { bg: "#f3e5f5", fg: "#6a1b9a", fallback: "借換" },
  other: { bg: "#f5f5f5", fg: "#424242", fallback: "その他" },
};

/** 生 action を正規化して種別を返す */
export function classifyBuyPlanAction(
  raw: string | null | undefined
): BuyPlanActionKind {
  const a = (raw || "").trim();
  if (!a) return "other";
  const lower = a.toLowerCase();

  if (/売却|売却予定|売渡|売主|exit|sell|sale/i.test(a) || lower.includes("sell")) {
    return "sale";
  }
  if (/借換|借り換|リファイナ|refi/i.test(a)) {
    return "refinance";
  }
  if (
    /調達|融資|借入|ローン|運転資金|フリー|カード|信用|枠|借入予定|資金調達|finance|loan/i.test(
      a
    )
  ) {
    return "finance";
  }
  if (
    /購入|買取|取得|買付|買い進め|新築|中古|buy|purchase|acquire/i.test(a)
  ) {
    return "purchase";
  }
  if (/買/.test(a) && !/売買/.test(a)) return "purchase";
  if (/売/.test(a)) return "sale";
  return "other";
}

/** 画面表示用（日本語ラベル＋色）。生値が日本語ならそれを優先表示 */
export function buyPlanActionView(
  raw: string | null | undefined
): BuyPlanActionView {
  const kind = classifyBuyPlanAction(raw);
  const style = KIND_STYLE[kind];
  const trimmed = (raw || "").trim();
  const label =
    trimmed && /[\u3040-\u30ff\u4e00-\u9fff]/.test(trimmed)
      ? trimmed
      : style.fallback + (trimmed ? `（${trimmed}）` : "");
  return {
    kind,
    label: trimmed ? label : style.fallback,
    bg: style.bg,
    fg: style.fg,
  };
}

export function isBuyAction(raw: string | null | undefined): boolean {
  return classifyBuyPlanAction(raw) === "purchase";
}

export function isSaleAction(raw: string | null | undefined): boolean {
  return classifyBuyPlanAction(raw) === "sale";
}
