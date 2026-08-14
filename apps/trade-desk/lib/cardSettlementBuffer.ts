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

export type TransferPhase = {
  id: string;
  title: string;
  timing: string;
  action: string;
  gate: string;
};

export type ScenarioExample = {
  id: "A" | "B" | "C" | "D";
  title: string;
  role: string;
  example: string;
};

/** money-ops assist_payload.rails[]（送金アシスト Wave 0） */
export type TransferRailStatus =
  | "pending"
  | "previewed"
  | "running"
  | "awaiting_final_confirm"
  | "otp_fetch"
  | "otp_submit"
  | "waiting_user"
  | "executing_click"
  | "verifying"
  | "done"
  | "failed"
  | "blocked"
  | "deferred";

export type TransferOtpChannel =
  | "gmail_api"
  | "sms_messages"
  | "app_onetime_pw"
  | "passkey_or_bio"
  | "none";

export type TransferRail = {
  id: string;
  label: string;
  amount_jpy: number;
  from_account_id: string;
  to_account_id: string;
  otp_channel: TransferOtpChannel;
  keep_floor_jpy?: number;
  status: TransferRailStatus;
  order?: number;
  free_rail?: boolean;
  idempotency_key?: string | null;
  evidence?: string | null;
  last_error?: string | null;
  /** iPhone で自分でやる手順（1行） */
  manual_iphone?: string;
  /** 実行の置き場 */
  where?: "iphone_app" | "mac_ib" | "either";
  /** 残す下限の説明 */
  keep_note?: string;
  /** リマインド（例: 明日朝・時間外明け） */
  remind_at?: string | null;
  /** ユーザー向け短いメモ */
  note?: string | null;
};

/**
 * 資金移動の鉄板 UX（ユーザー操作は3点だけ）
 * 1 プラン承認 → 2 Jarvis実行 → 3 最終画面確認 → 4 OTP＋実行ボタン
 */
export const FUND_MOVE_UX = {
  title: "資金移動の進め方",
  steps: [
    {
      id: "plan_approve",
      actor: "user" as const,
      label: "プランを承認する",
      detail: "money-ops で寄せ方に合意（この時点では資金は動かない）",
    },
    {
      id: "jarvis_execute",
      actor: "jarvis" as const,
      label: "Jarvis が入力・遷移する",
      detail: "ログイン・金額・宛先まで。実行クリックはしない",
    },
    {
      id: "final_confirm",
      actor: "user" as const,
      label: "最終画面を確認する",
      detail: "金額・手数料・宛先が意図どおりか見てから次へ",
    },
    {
      id: "otp_submit",
      actor: "user" as const,
      label: "OTP を入れて実行ボタン",
      detail: "ワンタイムPW／アプリ承認はユーザー。Jarvis は待機案内のみ",
    },
  ],
  user_only: ["plan_approve", "final_confirm", "otp_submit"] as const,
} as const;

export const RAIL_STATUS_LABEL: Record<TransferRailStatus, string> = {
  pending: "未着手",
  previewed: "プレビュー済",
  running: "Jarvis実行中",
  awaiting_final_confirm: "最終確認待ち",
  otp_fetch: "OTP取得中",
  otp_submit: "OTP入力中",
  waiting_user: "OTP／タップ待ち",
  executing_click: "実行クリック待ち",
  verifying: "証跡確認中",
  done: "完了",
  failed: "失敗",
  blocked: "ブロック",
  deferred: "延期",
};

/** Phase1 既定（config/kurashift_transfer_rails.yaml と同期） */
export const DEFAULT_TRANSFER_RAILS: TransferRail[] = [
  {
    id: "sbi_main_smbc",
    label: "第一生命NEOBANK本（普通）→SMBC刈谷",
    amount_jpy: 26000,
    from_account_id: "sbi_net_main",
    to_account_id: "smbc_kariya",
    otp_channel: "gmail_api",
    keep_floor_jpy: 500800,
    status: "pending",
    order: 10,
    free_rail: true,
    where: "either",
    keep_note: "残≈50.1万（Amex過渡）",
    manual_iphone:
      "第一生命NEOBANKアプリで本（普通）から三井住友刈谷へ26,000円（ことら可）。残50万超を維持",
  },
  {
    id: "sbi_sub_smbc",
    label: "第一生命NEOBANK副→SMBC刈谷",
    amount_jpy: 161000,
    from_account_id: "sbi_net_sub",
    to_account_id: "smbc_kariya",
    otp_channel: "gmail_api",
    keep_floor_jpy: 81000,
    status: "pending",
    order: 20,
    free_rail: true,
    where: "either",
    keep_note: "残≈8.1万",
    manual_iphone:
      "ことらで100,000＋61,000の2回。ハイブリッドなら先に普通へ戻してから。残≈8万維持",
  },
  {
    id: "tokairokin_smbc",
    label: "東海労金→SMBC刈谷",
    amount_jpy: 232000,
    from_account_id: "tokairokin",
    to_account_id: "smbc_kariya",
    otp_channel: "app_onetime_pw",
    keep_floor_jpy: 121000,
    status: "pending",
    order: 30,
    free_rail: false,
    where: "mac_ib",
    keep_note: "残≈12.1万",
    manual_iphone:
      "ワンタイムPWアプリ必須。IBはMac推奨。宛先=三井住友刈谷・232,000円",
  },
  {
    id: "mufg_airwallet",
    label: "MUFG豊明（千景）→IB→SMBC刈谷",
    amount_jpy: 290000,
    from_account_id: "mufg_toyoake",
    to_account_id: "smbc_kariya",
    otp_channel: "app_onetime_pw",
    keep_floor_jpy: 85000,
    status: "pending",
    order: 40,
    free_rail: false,
    where: "mac_ib",
    keep_note: "MUFG残≈8.5万。千景名義のため真治AW直結不可→今回はIB（手数料あり）",
    manual_iphone:
      "千景名義口座。エアウォレットは真治AWに紐づけ不可。IBで290,000＋手数料",
  },
  {
    id: "shiga_smbc",
    label: "滋賀銀行→SMBC刈谷",
    amount_jpy: 62000,
    from_account_id: "shiga",
    to_account_id: "smbc_kariya",
    otp_channel: "app_onetime_pw",
    keep_floor_jpy: 300000,
    status: "done",
    order: 50,
    where: "iphone_app",
    keep_note: "残≈30万（27日返済あり）。≤10万は AW 優先",
    manual_iphone:
      "エアウォレットで出金（≤10万即時）。IB はフォールバック（時間外 BEQB0003）",
  },
  {
    id: "kyoto_smbc",
    label: "京都銀行刈谷→SMBC刈谷",
    amount_jpy: 50000,
    from_account_id: "kyoto_kariya",
    to_account_id: "smbc_kariya",
    otp_channel: "app_onetime_pw",
    keep_floor_jpy: 51000,
    status: "done",
    order: 60,
    where: "iphone_app",
    keep_note: "残≈5.1万。≤10万は AW 優先",
    manual_iphone:
      "エアウォレットで出金（≤10万即時）。IB はフォールバック",
  },
];

/** iPhone 手動チェック用の進捗メタ（画面表示） */
export const MANUAL_EXEC_PROGRESS = {
  as_of: "2026-08-15",
  automation_status:
    "Phase1: NEOBANK本・副・東海労金・千景MUFG(IB)・滋賀(AW)・京都(AW) 完了。≤10万かつ紐づけ可はエアウォレット優先。",
  jarvis_continues_when:
    "残レール（PayPay等・blocked解除後）や次サイクルの寄せ。AW 対応銀行の週次お知らせを確認。",
  iphone_can:
    "エアウォレットでの出金（≤10万）、最終画面確認、money-ops のレール status 更新",
  needs_mac:
    "IB フォールバック時のみ --go と送金用 Chrome の後片付け",
} as const;

export const WHERE_LABEL: Record<NonNullable<TransferRail["where"]>, string> = {
  iphone_app: "iPhoneアプリ向き",
  mac_ib: "Mac IB向き",
  either: "iPhoneでも可",
};
export const TRANSFER_ASSIST_DOC =
  "docs/KURASHIFT_送金アシスト_実務者設計_20260814.md";

export function buildDefaultTransferRails(): TransferRail[] {
  return DEFAULT_TRANSFER_RAILS.map((r) => ({ ...r }));
}

/** Olive Infinite 引落の現金置き場（流動性マスタ正本） */
export const SMBC_SETTLEMENT_ACCOUNT_ID = "smbc_kariya";
export const SMBC_SETTLEMENT_ACCOUNT_LABEL = "三井住友銀行 刈谷";

export const CARD_SETTLEMENT_DOC =
  "docs/KURASHIFT_資金移動_カード引落バッファ_検討素案_20260814.md";

export const FREE_RAILS: FreeRail[] = [
  {
    id: "sbi_smbc",
    title: "第一生命NEOBANK ↔ 三井住友の無料振込枠",
    use: "月内寄せの本線。SBI余剰 → Olive（SMBC）",
    caution: "無料回数・時間帯を超えず有料化しない",
  },
  {
    id: "airwallet",
    title: "エアウォレット（COIN+／MUFGハブ）",
    use: "≤10万の即時寄せを優先。紐づけ可の口座間で無料チャージ／出金",
    caution: "同一名義のみ。千景MUFG豊明は真治AW不可。熱田・滋賀・京都は可",
  },
  {
    id: "cotra",
    title: "ことら送金",
    use: "対応アプリ間の無料即時（分割寄せ）",
    caution: "1件おおむね10万以下。100万超は分割",
  },
];

/**
 * 毎回使う本流。無料レールは「送る手段」、A〜D は「結果の比較例」であり、
 * この手順の分岐記号ではない。
 */
export const TRANSFER_PHASES: TransferPhase[] = [
  {
    id: "now",
    title: "いま動かせる余剰を寄せる",
    timing: "計画承認後",
    action: "各口座の次回引落とバッファを先に残し、確認済み余剰だけを引落口座へ送る",
    gate: "送金後残高が、その口座の残す下限を下回らない",
  },
  {
    id: "after_income",
    title: "入金先行を確認して追加で寄せる",
    timing: "家賃・売上などの着金後",
    action: "出金が先に来る口座は着金前に触らず、着金後の余剰だけを送る",
    gate: "次回のローン・固定費と安全バッファが残る",
  },
  {
    id: "after_salary",
    title: "給与後に不足を再計算する",
    timing: "給与着金後",
    action: "給与が引落口座へ直接入る分を反映し、まだ足りない額だけを再計算する",
    gate: "大垣・名銀など固定振分先の生活費を動かさない",
  },
  {
    id: "final_check",
    title: "引落前に最終確認する",
    timing: "引落日の2〜3営業日前",
    action: "引落口座残高が必要額以上か確認し、不足時だけ調達ラダーへ進む",
    gate: "同じ資金を二重計上せず、実残高で判定する",
  },
];

/** A〜D は本流を置き換える案ではなく、入金の効き方を見る感度分析の例。 */
export const SCENARIO_EXAMPLES: ScenarioExample[] = [
  {
    id: "A",
    title: "いま寄せる分だけ",
    role: "下限ケース",
    example: "Phase 1だけで、引落口座にあといくら足りないかを見る",
  },
  {
    id: "B",
    title: "A＋給与が少なめ",
    role: "慎重ケース",
    example: "給与の引落口座入金が想定より少ない場合の不足を見る",
  },
  {
    id: "C",
    title: "A＋通常給与",
    role: "本命ケース",
    example: "安定している通常給与を反映し、引落を満たすか判断する",
  },
  {
    id: "D",
    title: "C＋家賃・売上着金後の余剰",
    role: "安全余裕ケース",
    example: "出金先行口座の着金後余剰まで加え、引落後バッファを確認する",
  },
];

/** IFA推奨順（ユーザー案 a→b→c から b/c 入替・コア売却を最後へ） */
export const FUNDING_LADDER: FundingStep[] = [
  {
    order: 0,
    id: "bank_consolidate",
    title: "銀行内の無料寄せ（無料レール3本）",
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
    "【本流1】各行に当月固定引落＋バッファを先に残し、いま動かせる余剰だけ寄せる",
    "【本流2】出金先行口座は家賃・売上の着金後にだけ再計算して追加で寄せる",
    "【本流3】給与着金後に不足を再計算し、引落2〜3営業日前に実残高で最終確認する",
    "【送金手段】無料レール: SBI↔SMBC無料枠／ことら分割（〜10万/件）／エアウォレット（MUFGハブ）。本流の別案ではない",
    "【結果例A〜D】Phase後の残高を比べる感度分析。本流の分岐ではなく、A=下限・B=慎重・C=本命・D=安全余裕",
    "【不足時だけ】調達ラダー: 利金送金 →（定額返済カレンダー可なら）契約者貸付 → Bloomo一部 →（最終）SBIコアは原則禁止",
    "定額返済を書けるなら貸付は可（防衛・次物件・NISA9万の余りから）。書けないなら Bloomo 優先",
    "あかつき元本売却は使わない",
    "【鉄板UX】①プラン承認 → ②Jarvis入力 → ③最終画面確認 → ④OTP＋実行ボタン（ユーザーは①③④のみ）",
    "【手動チェック】iPhone: 最終確認とOTP。Mac: IB自動化。承認だけでは資金は動かない",
    "承認＝計画合意のみ。実行はレールごと。メール／SMS OTPはJarvis、アプリOTPはユーザー",
    "各レール完了は証跡付きで rails[].status=done。レール終了後は送金用Chromeを閉じる",
    "オペ全体の done で引落アラート解除",
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
