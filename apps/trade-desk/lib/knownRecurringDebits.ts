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
/** 2026-10-18: 解約済 Preferred 残債 10,860円／月 → ドコモSMTB イチゴ（〜2027-07想定） */
export const KNOWN_RECURRING_DEBITS: KnownRecurringDebit[] = [
  {
    id: "smcc_preferred_residual_docomo_smtb",
    label: "解約済 Preferred（Visa）残債引落",
    settlementAccountId: "sbi_net_main",
    settlementBankLabel: "ドコモSMTBネット銀行 イチゴ支店",
    excludeFromAccountIds: [
      "sbi_net_sub",
      "smbc_kariya",
      "mufg_atsuta",
      "mufg_toyoake",
    ],
    dayOfMonth: 26,
    amountJpyApprox: 10_860,
    evidenceStatus: "user_confirm",
    note:
      "解約済みでも毎月26日に10,860円。active_until≈2027-07。SBI本からの資金移動で先に残す。年会費とは別。",
  },
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
