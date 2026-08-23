/**
 * 定期引落の学習オーバーライド（Zaim実績が薄いもの）。
 * 正本 YAML: config/known_recurring_debits.yaml
 * Jarvis / money-ops が口座バッファを見るとき、実績より先にここを参照する想定。
 */
export type KnownRecurringDebit = {
  id: string;
  label: string;
  settlementAccountId: string;
  settlementBankLabel: string;
  /** この口座ID群のバッファ計算に月額を足さない */
  excludeFromAccountIds: string[];
  dayOfMonth: number;
  amountJpyApprox: number;
  evidenceStatus: "pending_zaim" | "zaim_observed" | "user_confirm";
  note: string;
};

/** 2026-08-23 ユーザー学習: BMW/MINI は三菱UFJ熱田。SBIではない。 */
export const KNOWN_RECURRING_DEBITS: KnownRecurringDebit[] = [
  {
    id: "bmw_mini_mufg_mycar",
    label: "BMW/MINI ネットDEマイカーローン",
    settlementAccountId: "mufg_atsuta",
    settlementBankLabel: "三菱UFJ銀行 熱田",
    excludeFromAccountIds: [
      "sbinet",
      "sbi_net_main",
      "sbi_net_sub",
      "mufg_toyoake",
      "smbc_kariya",
    ],
    dayOfMonth: 21,
    amountJpyApprox: 32_426,
    evidenceStatus: "pending_zaim",
    note: "実績はこれから。SBIカード引落計画に混ぜない。豊明≠返済口座。",
  },
];

export function knownDebitsForAccount(
  accountId: string,
): KnownRecurringDebit[] {
  return KNOWN_RECURRING_DEBITS.filter(
    (d) => d.settlementAccountId === accountId,
  );
}

export function shouldExcludeDebitFromAccountBuffer(
  debitId: string,
  accountId: string,
): boolean {
  const d = KNOWN_RECURRING_DEBITS.find((x) => x.id === debitId);
  return Boolean(d?.excludeFromAccountIds.includes(accountId));
}
