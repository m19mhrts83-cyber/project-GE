/** ③-C 物件マスタ最小揃え（写し）。正本: config/kurashift_re_property_master.yaml */

export type RePropertyBook = {
  bodyPriceJpy: number | null;
  buildingJpy: number | null;
  equipmentJpy: number | null;
  landJpy: number | null;
  buildingYears: number | null;
  equipmentYears: number | null;
  allocation: "estimated" | "confirmed" | null;
  note: string | null;
};

export type RePropertyMaster = {
  id: string;
  name: string;
  owner: string;
  ownerEntity: string;
  /** personal | corporate */
  entity: "personal" | "corporate";
  acquired: string;
  /** 7桁ハイフン付き（例: 462-0834） */
  postalCode: string;
  address: string;
  /** Notion「所有物件関係」DB_物件情報の鍵番号。null は「なし」 */
  keyNumber: number | null;
  roomsExpected: number;
  managers: string[];
  loanIds: string[];
  book: RePropertyBook | null;
  /** 物件紐づけ用ヒント（口座・摘要） */
  matchHints: string[];
};

export const RE_PROPERTY_MASTER: RePropertyMaster[] = [
  {
    id: "grandole-i",
    name: "Grandole志賀本通Ⅰ",
    owner: "法人",
    ownerEntity: "リビングサポート松",
    entity: "corporate",
    acquired: "2025-02-28",
    postalCode: "462-0834",
    address: "愛知県名古屋市北区長田町4丁目69番地5",
    keyNumber: 2842,
    roomsExpected: 8,
    managers: ["LEAF", "Tcell"],
    loanIds: ["orix-g1-corp"],
    book: {
      bodyPriceJpy: 68_532_000,
      buildingJpy: 34_266_000,
      equipmentJpy: 6_853_200,
      landJpy: 27_412_800,
      buildingYears: 47,
      equipmentYears: 15,
      allocation: "estimated",
      note: "本体=ROI。按分 建物50%/設備10%/土地40%（概算）",
    },
    matchHints: ["grandole", "志賀本通", "Ⅰ", "I", "アパート経営"],
  },
  {
    id: "grandole-ii",
    name: "Grandole志賀本通Ⅱ",
    owner: "個人",
    ownerEntity: "松野真治",
    entity: "personal",
    acquired: "2022-09",
    postalCode: "462-0834",
    address: "愛知県名古屋市北区長田町4丁目69番地5",
    keyNumber: 1555,
    roomsExpected: 8,
    managers: ["ホームプランナー"],
    loanIds: ["orix-g2-pers"],
    book: {
      bodyPriceJpy: 69_800_000,
      buildingJpy: 34_900_000,
      equipmentJpy: 6_980_000,
      landJpy: 27_920_000,
      buildingYears: 47,
      equipmentYears: 15,
      allocation: "estimated",
      note: "本体=ROI。按分 建物50%/設備10%/土地40%（概算）",
    },
    matchHints: ["grandole", "志賀本通", "Ⅱ", "II"],
  },
  {
    id: "caramel",
    name: "キャラメル",
    owner: "個人",
    ownerEntity: "松野真治",
    entity: "personal",
    acquired: "2025-12-26",
    postalCode: "459-8008",
    address: "愛知県名古屋市緑区文久山418",
    keyNumber: null,
    roomsExpected: 4,
    managers: ["Tcell"],
    loanIds: ["shiga-caramel", "shiga-caramel-cost"],
    book: {
      bodyPriceJpy: 46_000_000,
      buildingJpy: 23_000_000,
      equipmentJpy: 4_600_000,
      landJpy: 18_400_000,
      buildingYears: 22,
      equipmentYears: 15,
      allocation: "estimated",
      note: "本体=ROI。木造想定・建物耐用22年。按分は概算",
    },
    matchHints: ["キャラメル", "caramel", "文久山"],
  },
];

export type LoanLike = {
  id: string;
  name: string | null;
  tags?: string[] | null;
  payload?: Record<string, unknown> | null;
  category_major?: string | null;
};

/** 物件 id に紐づくローン（プライベート借入は除外） */
export function loansForProperty<T extends LoanLike>(
  propertyId: string,
  loans: T[]
): T[] {
  const master = RE_PROPERTY_MASTER.find((p) => p.id === propertyId);
  const wanted = new Set(master?.loanIds || []);
  return loans.filter((loan) => {
    if (wanted.has(loan.id)) return true;
    const payload = (loan.payload || {}) as Record<string, unknown>;
    const pid = String(payload.propertyId || payload.property_id || "");
    if (pid === propertyId) {
      const major = String(loan.category_major || "");
      if (major === "その他" || major === "プライベート") return false;
      return true;
    }
    const tags = (loan.tags || []).map(String);
    return tags.includes(propertyId);
  });
}

export function getRePropertyMaster(id: string): RePropertyMaster | null {
  return RE_PROPERTY_MASTER.find((p) => p.id === id) || null;
}

/** 郵便番号を 〒123-4567 形式にする */
export function fmtPostalCode(code: string | null | undefined): string {
  const raw = (code || "").trim();
  if (!raw) return "—";
  const digits = raw.replace(/\D/g, "");
  if (digits.length === 7) return `〒${digits.slice(0, 3)}-${digits.slice(3)}`;
  if (raw.startsWith("〒")) return raw;
  return `〒${raw}`;
}

/** 鍵番号。未設定は「なし」と明記する */
export function fmtKeyNumber(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "なし";
  return String(n);
}

export function formatMasterLocation(
  p: Pick<RePropertyMaster, "postalCode" | "address">
): string {
  return `${fmtPostalCode(p.postalCode)} ${p.address}`.trim();
}
