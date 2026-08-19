/**
 * 家計B/S — 助言パネル（Phase D）
 * jarvis-finance-philosophy: 防衛→次物件→NISA→Theme
 */

import type { HouseholdBsView } from "./householdBsCompose";
import { fmtManRounded } from "./format";

export type AdviceItem = {
  order: number;
  label: string;
  amountJpy: number | null;
  status: "ok" | "watch" | "info";
  href?: string;
  note?: string;
};

export function buildHouseholdAdvice(view: HouseholdBsView): AdviceItem[] {
  const cashRows = view.rows.filter(
    (r) => r.band === "cash" && r.countsTowardTotal && r.amountJpy != null
  );
  const cashTotal = cashRows.reduce((s, r) => s + (r.amountJpy ?? 0), 0);

  const nextProperty = view.rows
    .filter((r) => r.band === "next_property" && r.indent)
    .reduce((s, r) => s + (r.amountJpy ?? 0), 0);

  const sleepTotal = view.rows
    .filter((r) => r.band === "sleep" && r.countsTowardTotal)
    .reduce((s, r) => s + (r.amountJpy ?? 0), 0);

  const themeTotal = view.rows
    .filter((r) => r.band === "theme" && r.countsTowardTotal)
    .reduce((s, r) => s + (r.amountJpy ?? 0), 0);

  const bridgeLiab = view.rows.find((r) => r.id === "card_debit_pending");

  return [
    {
      order: 1,
      label: "生活防衛＋物件バッファ（現金）",
      amountJpy: cashTotal > 0 ? cashTotal : null,
      status: cashTotal > 0 ? "ok" : "watch",
      href: "/money-ops",
      note: "liquidity_snapshots 合計",
    },
    {
      order: 2,
      label: "次物件キープ（契約者貸付・参考）",
      amountJpy: nextProperty > 0 ? nextProperty : null,
      status: nextProperty > 0 ? "info" : "watch",
      href: "/realestate/buy-plan",
      note: "保険ネットに反映済み。合計二重なし",
    },
    {
      order: 3,
      label: "NISA月9万（寝かせてコア）",
      amountJpy: sleepTotal > 0 ? sleepTotal : null,
      status: "ok",
      href: "/portfolio",
      note: "SBIコア等。触らない・売らない",
    },
    {
      order: 4,
      label: "Theme / Bloomo衛星",
      amountJpy: themeTotal > 0 ? themeTotal : null,
      status: "info",
      href: "/portfolio",
      note: "防衛・次物件の上だけ",
    },
    {
      order: 5,
      label: "クレカ引落（ブリッジ）",
      amountJpy: bridgeLiab?.amountJpy ?? null,
      status: bridgeLiab?.amountJpy ? "watch" : "ok",
      href: "/money-ops",
      note: bridgeLiab?.hint,
    },
  ];
}

export function formatAdviceAmount(n: number | null): string {
  if (n == null || !Number.isFinite(n)) return "要確認";
  return fmtManRounded(n);
}
