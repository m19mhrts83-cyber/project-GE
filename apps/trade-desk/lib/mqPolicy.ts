/**
 * MQ会計評価 — 運用方針（顧客確定 2026-08-16）
 *
 * 1. B/S初期: ローン残高トラッカーで他人資本を補正 + 税理士試算表等は手入力
 * 2. 現金: 個人家計現金を不動産B/Sに含める（リアル現金=参考）。期次で締め、繰越で増減を積む。
 *    財務主眼のため年別クローズ→翌年へ繰入を基本とする（会計期とずれることあり）
 * 3. AI の Q: 案件数（補助KPI）
 */

export const MQ_POLICY = {
  cashIncludesHousehold: true,
  cashNote:
    "現金は家計含む参考値。事業の増減は期次締め→繰越で積む（年別クローズ基本）。",
  bsLoanSource: "loan_tracker" as const,
  bsManualOk: true,
  aiQUnit: "案件数" as const,
  realestateQUnit: "稼働戸月" as const,
  /** 先月まとめ促し: 翌月1〜10日（JST） */
  monthCloseWindowDays: [1, 10] as const,
} as const;

export function qUnitLabel(businessLine: string): string {
  if (businessLine === "ai") return MQ_POLICY.aiQUnit;
  return MQ_POLICY.realestateQUnit;
}

export function qFieldLabel(businessLine: string): string {
  return `Q（${qUnitLabel(businessLine)}）`;
}
