/** 融資提出パック書類カタログ（写し）。正本: config/kurashift_re_finance_doc_templates.yaml */

export type Ownership = "common" | "personal" | "corporate";
export type ProductType =
  | "property_purchase"
  | "working_capital"
  | "free_loan"
  | "education_loan";
export type DocLayer = "always" | "deal";

export type FinanceDocSlot = {
  id: string;
  title: string;
  layer: DocLayer;
  ownership: Ownership;
  product_types: ProductType[];
  media?: "digital" | "mail_original";
  how?: string;
  path_hint?: string;
  data_source?: string;
};

export type BankProfile = {
  id: string;
  label: string;
  product_types: ProductType[];
  extra_slot_ids: string[];
  note: string;
};

export const PRODUCT_TYPE_LABELS: Record<ProductType, string> = {
  property_purchase: "物件購入融資",
  working_capital: "運転資金",
  free_loan: "フリーローン",
  education_loan: "教育ローン",
};

export const OWNERSHIP_LABELS: Record<Ownership, string> = {
  common: "共通",
  personal: "個人",
  corporate: "法人",
};

const COMMON: FinanceDocSlot[] = [
  {
    id: "mynumber_card",
    title: "マイナンバーカード（券面コピー）",
    layer: "always",
    ownership: "common",
    product_types: [
      "property_purchase",
      "working_capital",
      "free_loan",
      "education_loan",
    ],
    media: "digital",
    how: "スキャナ／スマホ。表面・裏面",
    path_hint: "00_共通/マイナンバーカード",
  },
  {
    id: "drivers_license",
    title: "運転免許証（表裏）",
    layer: "always",
    ownership: "common",
    product_types: [
      "property_purchase",
      "working_capital",
      "free_loan",
      "education_loan",
    ],
    media: "digital",
    how: "スキャナ。実物参照: 243_カードローン書類",
    path_hint: "00_共通/免許証",
  },
  {
    id: "health_insurance_card",
    title: "健康保険証（表裏）",
    layer: "always",
    ownership: "common",
    product_types: [
      "property_purchase",
      "working_capital",
      "free_loan",
      "education_loan",
    ],
    media: "digital",
    how: "スキャナ",
    path_hint: "00_共通/保険証",
  },
  {
    id: "existing_loans_list",
    title: "既存借入一覧・残高（as-of）",
    layer: "always",
    ownership: "common",
    product_types: [
      "property_purchase",
      "working_capital",
      "free_loan",
      "education_loan",
    ],
    media: "digital",
    how: "借入残高トラッカー → loans.json",
    path_hint: "03_既存借入/",
    data_source: "loan_tracker",
  },
];

const PERSONAL: FinanceDocSlot[] = [
  {
    id: "withholding_3y",
    title: "源泉徴収票（直近〜3期）",
    layer: "always",
    ownership: "personal",
    product_types: [
      "property_purchase",
      "free_loan",
      "education_loan",
      "working_capital",
    ],
    media: "digital",
    how: "smartHR／勤務先",
    path_hint: "02_収入税務/源泉",
  },
  {
    id: "tax_return_personal",
    title: "確定申告書控（直近）",
    layer: "always",
    ownership: "personal",
    product_types: [
      "property_purchase",
      "free_loan",
      "education_loan",
      "working_capital",
    ],
    media: "digital",
    how: "e-Tax",
    path_hint: "02_収入税務/確定申告",
  },
  {
    id: "residence_certificate",
    title: "住民票",
    layer: "always",
    ownership: "personal",
    product_types: ["property_purchase", "free_loan", "education_loan"],
    media: "mail_original",
    how: "コンビニ交付／区役所",
    path_hint: "01_個人/住民票",
  },
  {
    id: "seal_certificate",
    title: "印鑑証明書",
    layer: "always",
    ownership: "personal",
    product_types: ["property_purchase"],
    media: "mail_original",
    how: "物件決済前後で要原本が多い",
    path_hint: "01_個人/印鑑証明",
  },
  {
    id: "personal_assets_snapshot",
    title: "資産残高（預金・証券・保険等）",
    layer: "always",
    ownership: "personal",
    product_types: ["property_purchase", "free_loan", "education_loan"],
    media: "digital",
    how: "各社マイページ／週次資産",
    path_hint: "04_資産/",
  },
  {
    id: "personal_profile",
    title: "身上書",
    layer: "always",
    ownership: "personal",
    product_types: ["property_purchase"],
    media: "digital",
    how: "241_融資審査/身上書",
    path_hint: "01_個人/身上書",
  },
];

const CORPORATE: FinanceDocSlot[] = [
  {
    id: "corp_registry",
    title: "履歴事項全部証明書（3カ月以内原本）",
    layer: "always",
    ownership: "corporate",
    product_types: ["property_purchase", "working_capital"],
    media: "mail_original",
    how: "法務局。名銀口座時も必須",
    path_hint: "01_法人/履歴事項全部証明書",
  },
  {
    id: "corp_articles",
    title: "定款",
    layer: "always",
    ownership: "corporate",
    product_types: ["property_purchase", "working_capital"],
    media: "digital",
    how: "名銀口座時も必須",
    path_hint: "01_法人/定款",
  },
  {
    id: "corp_seal",
    title: "法人記名版・銀行届印",
    layer: "always",
    ownership: "corporate",
    product_types: ["property_purchase", "working_capital"],
    media: "mail_original",
    how: "窓口持参",
    path_hint: "01_法人/印鑑",
  },
  {
    id: "corp_financials_2y",
    title: "決算書・確定申告（前期・前々期）",
    layer: "always",
    ownership: "corporate",
    product_types: ["property_purchase", "working_capital"],
    media: "digital",
    how: "税理士。マル経も同型",
    path_hint: "02_収入税務/決算",
  },
  {
    id: "corp_trial_balance",
    title: "直近残高試算表（決算後6カ月超のとき）",
    layer: "always",
    ownership: "corporate",
    product_types: ["working_capital"],
    media: "digital",
    how: "税理士",
    path_hint: "02_収入税務/試算表",
  },
  {
    id: "corp_tax_receipts",
    title: "法人税等の納税証明・領収書",
    layer: "always",
    ownership: "corporate",
    product_types: ["working_capital", "property_purchase"],
    media: "digital",
    how: "マル経必須",
    path_hint: "02_収入税務/納税",
  },
  {
    id: "guarantor_income",
    title: "代表者個人の収入証明（保証・併走）",
    layer: "always",
    ownership: "corporate",
    product_types: ["property_purchase", "working_capital"],
    media: "digital",
    how: "01_法人/代表者個人/",
    path_hint: "01_法人/代表者個人/収入",
  },
];

const DEAL_PROPERTY: FinanceDocSlot[] = [
  {
    id: "property_flyer",
    title: "マイソク／図面",
    layer: "deal",
    ownership: "common",
    product_types: ["property_purchase"],
    media: "digital",
    path_hint: "05_物件または使途根拠/図面",
  },
  {
    id: "rent_roll",
    title: "レントロール",
    layer: "deal",
    ownership: "common",
    product_types: ["property_purchase"],
    media: "digital",
    path_hint: "05_物件または使途根拠/レントロール",
  },
  {
    id: "property_registry",
    title: "謄本・公図",
    layer: "deal",
    ownership: "common",
    product_types: ["property_purchase"],
    media: "digital",
    path_hint: "05_物件または使途根拠/登記",
  },
  {
    id: "sale_contract",
    title: "売買契約・重要事項説明",
    layer: "deal",
    ownership: "common",
    product_types: ["property_purchase"],
    media: "digital",
    path_hint: "06_取引契約/",
  },
  {
    id: "offer_sheet",
    title: "買付申込",
    layer: "deal",
    ownership: "common",
    product_types: ["property_purchase"],
    media: "digital",
    path_hint: "06_取引契約/買付",
  },
];

const DEAL_UNSECURED: FinanceDocSlot[] = [
  {
    id: "purpose_estimate",
    title: "資金使途確認（見積書・注文書・請求書）",
    layer: "deal",
    ownership: "common",
    product_types: ["free_loan", "working_capital"],
    media: "digital",
    how: "フリーローン必須パターン",
    path_hint: "05_物件または使途根拠/見積",
  },
  {
    id: "education_payment_slip",
    title: "学校納付書・振込用紙・在学証明",
    layer: "deal",
    ownership: "personal",
    product_types: ["education_loan"],
    media: "digital",
    path_hint: "05_物件または使途根拠/教育",
  },
  {
    id: "repair_history",
    title: "修繕履歴・修繕計画（運転資金根拠）",
    layer: "deal",
    ownership: "corporate",
    product_types: ["working_capital"],
    media: "digital",
    how: "商工会相談実績",
    path_hint: "05_物件または使途根拠/修繕",
  },
  {
    id: "marukei_guidance_status",
    title: "商工会・経営指導ステータス／相談日",
    layer: "deal",
    ownership: "corporate",
    product_types: ["working_capital"],
    media: "digital",
    how: "マル経は指導・推薦が前提",
    path_hint: "07_銀行固有/マル経",
  },
];

export const ALL_FINANCE_SLOTS: FinanceDocSlot[] = [
  ...COMMON,
  ...PERSONAL,
  ...CORPORATE,
  ...DEAL_PROPERTY,
  ...DEAL_UNSECURED,
];

export const BANK_PROFILES: BankProfile[] = [
  {
    id: "orix",
    label: "オリックス銀行（物件）",
    product_types: ["property_purchase"],
    extra_slot_ids: [],
    note: "GrandoleⅠ・Ⅱ実績",
  },
  {
    id: "shiga",
    label: "滋賀銀行ジャストサポート",
    product_types: ["property_purchase", "free_loan"],
    extra_slot_ids: [],
    note: "キャラメル本担保＋諸費用。無担保枠注意",
  },
  {
    id: "meigin",
    label: "名古屋銀行",
    product_types: ["working_capital", "education_loan", "property_purchase"],
    extra_slot_ids: ["corp_registry", "corp_articles", "corp_seal"],
    note: "法人口座・運転資金相談・教育ローン既存",
  },
  {
    id: "marukei",
    label: "マル経（商工会→公庫）",
    product_types: ["working_capital"],
    extra_slot_ids: [
      "corp_financials_2y",
      "corp_trial_balance",
      "corp_tax_receipts",
      "corp_registry",
      "repair_history",
      "marukei_guidance_status",
    ],
    note: "無担保・無保証人。指導期間あり",
  },
  {
    id: "free_loan_generic",
    label: "フリーローン（汎用）",
    product_types: ["free_loan"],
    extra_slot_ids: [
      "purpose_estimate",
      "withholding_3y",
      "tax_return_personal",
    ],
    note: "本人確認＋年収＋使途確認",
  },
  {
    id: "education_generic",
    label: "教育ローン（汎用）",
    product_types: ["education_loan"],
    extra_slot_ids: ["education_payment_slip", "withholding_3y"],
    note: "名銀・住信SBI既存",
  },
];

export function filterFinanceSlots(opts: {
  productType: ProductType;
  ownership: "personal" | "corporate";
  bankId?: string | null;
}): FinanceDocSlot[] {
  const { productType, ownership, bankId } = opts;
  const byId = new Map(ALL_FINANCE_SLOTS.map((s) => [s.id, s]));
  const out: FinanceDocSlot[] = [];
  const seen = new Set<string>();

  const push = (s: FinanceDocSlot | undefined) => {
    if (!s || seen.has(s.id)) return;
    if (!s.product_types.includes(productType)) return;
    if (s.ownership === "common") {
      seen.add(s.id);
      out.push(s);
      return;
    }
    if (s.ownership !== ownership) return;
    seen.add(s.id);
    out.push(s);
  };

  for (const s of ALL_FINANCE_SLOTS) push(s);

  const bank = BANK_PROFILES.find((b) => b.id === bankId);
  if (bank) {
    for (const id of bank.extra_slot_ids) push(byId.get(id));
  }

  // 共通 → 名義 → 常備 → 案件の順
  const rank = (s: FinanceDocSlot) => {
    const o =
      s.ownership === "common" ? 0 : s.ownership === ownership ? 1 : 2;
    const l = s.layer === "always" ? 0 : 1;
    return o * 10 + l;
  };
  return out.sort((a, b) => rank(a) - rank(b) || a.title.localeCompare(b.title, "ja"));
}

export function buildShortageText(
  slots: FinanceDocSlot[],
  status: Record<string, string>,
  meta: { productLabel: string; ownershipLabel: string; bankLabel: string }
): string {
  const missing = slots.filter((s) => {
    const st = status[s.id] || "todo";
    return st === "todo" || st === "need_original";
  });
  const lines = [
    `【融資提出パック・不足一覧】`,
    `商品: ${meta.productLabel} / 名義: ${meta.ownershipLabel} / 先: ${meta.bankLabel}`,
    ``,
    ...missing.map(
      (s) =>
        `- [ ] ${s.title}${s.media === "mail_original" ? "（原本）" : ""} ${s.path_hint ? `→ ${s.path_hint}` : ""}`
    ),
  ];
  if (missing.length === 0) lines.push("- （不足なし）");
  return lines.join("\n");
}

export function buildEmailDraft(opts: {
  productLabel: string;
  bankLabel: string;
  ownershipLabel: string;
  amountNote?: string;
  shortageText: string;
}): string {
  return [
    `件名: 【ご相談】${opts.productLabel}の件（リビングサポート松／松野）`,
    ``,
    `${opts.bankLabel} ご担当者様`,
    ``,
    `お世話になっております。`,
    `リビングサポート松の松野です。`,
    ``,
    `${opts.productLabel}（${opts.ownershipLabel}）についてご相談させてください。`,
    opts.amountNote ? `希望の目安: ${opts.amountNote}` : "",
    ``,
    `準備状況（不足があればご指摘ください）:`,
    opts.shortageText,
    ``,
    `ご多忙のところ恐れ入りますが、ご確認のほどよろしくお願いいたします。`,
    ``,
    `松野`,
  ]
    .filter((l) => l !== "")
    .join("\n");
}
