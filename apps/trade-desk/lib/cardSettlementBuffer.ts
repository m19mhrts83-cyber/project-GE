/** カード引落バッファ — 無料レール＋調達ラダー（検討素案の正本写し） */

export type FundingStep = {
  order: number;
  id: string;
  title: string;
  verdict: "必須" | "推奨" | "条件付き" | "最終手段" | "不可";
  note: string;
};

export type FreeRail = {
  id: string;
  title: string;
  use: string;
  caution: string;
};

/** Olive Infinite 引落の現金置き場（流動性マスタ正本） */
export const SMBC_SETTLEMENT_ACCOUNT_ID = "smbc_kariya";
export const SMBC_SETTLEMENT_ACCOUNT_LABEL = "三井住友銀行 刈谷";

export const CARD_SETTLEMENT_DOC =
  "docs/KURASHIFT_資金移動_カード引落バッファ_検討素案_20260814.md";

export const FREE_RAILS: FreeRail[] = [
  {
    id: "sbi_smbc",
    title: "住信SBI ↔ 三井住友の無料振込枠",
    use: "月内寄せの本線。SBI余剰 → Olive（SMBC）",
    caution: "無料回数・時間帯を超えず有料化しない",
  },
  {
    id: "airwallet",
    title: "エアウォレット（COIN+／MUFGハブ）",
    use: "MUFG系↔他行の無料チャージ／出金／送金",
    caution: "出金先が引落口座に届くか初回だけ実機確認",
  },
  {
    id: "cotra",
    title: "ことら送金",
    use: "対応アプリ間の無料即時（分割寄せ）",
    caution: "1件おおむね10万以下。100万超は分割",
  },
];

/** IFA推奨順（ユーザー案 a→b→c から b/c 入替・コア売却を最後へ） */
export const FUNDING_LADDER: FundingStep[] = [
  {
    order: 0,
    id: "bank_consolidate",
    title: "銀行内の無料寄せ（レールA〜C）",
    verdict: "必須",
    note: "資産を崩さない。ギャップの第一対応",
  },
  {
    order: 1,
    id: "bond_coupon_cash",
    title: "海外債の既入金利金・余剰現金を送金",
    verdict: "推奨",
    note: "あかつき元本は売らない。口座に溜まった利金のみ",
  },
  {
    order: 2,
    id: "policy_loan",
    title: "契約者貸付（既存ソニー等）で短期ブリッジ",
    verdict: "条件付き",
    note: "常態化禁止。返済原資必須。定額返済カレンダー（月額・期間・原資）が書けるときOK。防衛・次物件・NISA9万の余りから。書けないなら Bloomo 優先",
  },
  {
    order: 3,
    id: "bloomo_partial",
    title: "Bloomo（衛星）の一部売却",
    verdict: "条件付き",
    note: "返済枠が給与に乗らないとき／宿題を早く閉じたいとき。再建は余り枠で任意",
  },
  {
    order: 4,
    id: "sbi_core_sale",
    title: "SBIインデックス（コア）売却",
    verdict: "最終手段",
    note: "寝かせて方針に反する。明示合意があるときだけ",
  },
];

/** フォーム・アシストに出す貸付の注記（1行） */
export const POLICY_LOAN_UI_NOTE =
  "契約者貸付は短期ブリッジのみ・常態化禁止・返済原資必須。定額返済を書けるなら可（株再建と同型）。書けない／防衛・NISAを削るなら衛星清算を優先";

export type GapView = {
  /** 引落口座に足りない額（寄せの目標） */
  smbcShortfall: number;
  /** 家計の銀行＋現金合計から見て、調達ラダーが要りそうか */
  householdCoverable: boolean | null;
  otherBanksYen: number | null;
};

export function computeGapView(input: {
  needYen: number;
  smbcYen: number;
  reserveYen: number;
  liquidityTotalYen?: number | null;
}): GapView {
  const usable = Math.max(0, input.smbcYen - (input.reserveYen || 0));
  const smbcShortfall = input.needYen - usable;
  const liq = input.liquidityTotalYen;
  if (liq == null || !Number.isFinite(liq)) {
    return { smbcShortfall, householdCoverable: null, otherBanksYen: null };
  }
  const other = Math.max(0, liq - input.smbcYen);
  return {
    smbcShortfall,
    householdCoverable: smbcShortfall <= 0 ? true : other >= smbcShortfall,
    otherBanksYen: other,
  };
}

export function buildCardSettlementAssistSteps(input: {
  dueDate?: string;
  needYen?: number | null;
  smbcYen?: number | null;
  gapView?: GapView | null;
}): string[] {
  const need =
    input.needYen != null && Number.isFinite(input.needYen)
      ? `${Math.round(input.needYen).toLocaleString("ja-JP")}円`
      : "（必要額を明細で確定）";
  const smbc =
    input.smbcYen != null && Number.isFinite(input.smbcYen)
      ? `${Math.round(input.smbcYen).toLocaleString("ja-JP")}円`
      : "（SMBC残高を再取得）";
  const due = input.dueDate?.trim() || "（引落日をVpassで確定）";
  const short =
    input.gapView && Number.isFinite(input.gapView.smbcShortfall)
      ? `${Math.round(input.gapView.smbcShortfall).toLocaleString("ja-JP")}円`
      : "（計算）";
  const cover =
    input.gapView?.householdCoverable === true
      ? "他行寄せで足りそう（調達ラダーは原則不要）"
      : input.gapView?.householdCoverable === false
        ? "他行寄せだけでは足りない可能性 → 調達ラダー検討"
        : "他行合計は画面で確認";
  return [
    `引落日 ${due}・必要額 ${need}・${SMBC_SETTLEMENT_ACCOUNT_LABEL} ${smbc}`,
    `SMBC不足（寄せ目標） ${short} — ${cover}`,
    "各行に当月固定引落＋バッファだけ残し、余剰を洗い出す",
    "無料レール: ①SBI↔SMBC無料枠 ②ことら分割（〜10万/件）③エアウォレット（MUFGハブ）",
    "なお不足なら調達ラダー: 利金送金 →（定額返済カレンダー可なら）契約者貸付 → Bloomo一部 →（最終）SBIコアは原則禁止",
    "定額返済を書けるなら貸付は可（防衛・次物件・NISA9万の余りから）。書けないなら Bloomo 優先",
    "あかつき元本売却は使わない",
    "承認後も振込は手動。実行したら status を executing→done に更新（done で引落アラート解除）",
  ];
}

export function defaultCardSettlementRationale(input: {
  needYen?: number | null;
  dueDate?: string;
  gapView?: GapView | null;
}): string {
  const need =
    input.needYen != null && Number.isFinite(input.needYen)
      ? `必要額 ${Math.round(input.needYen).toLocaleString("ja-JP")}円`
      : "必要額100万円超（確定額は明細）";
  const due = input.dueDate?.trim() || "引落日未確定";
  const cover =
    input.gapView?.householdCoverable === true
      ? "他行寄せで足りそう。"
      : input.gapView?.householdCoverable === false
        ? "他行寄せ後も不足の可能性あり。"
        : "";
  return [
    `Olive Infinite カード引落バッファ（${due}）。${need}。${cover}`,
    "無料レールでSMBCへ寄せ、不足時は利金→（定額返済可なら）貸付→Bloomoの順。",
    "定額返済カレンダーを書ける貸付は可。防衛・次物件・NISA9万を削るなら不可。衛星売却は宿題を早く閉じるとき。",
    "あかつき元本・SBIコア売却は原則しない。詳細は docs/KURASHIFT_資金移動_カード引落バッファ_検討素案_20260814.md",
  ].join(" ");
}
