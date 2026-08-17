/** ③-C 物件マスタ最小揃え（写し）。正本: config/kurashift_re_property_master.yaml */

export type RePropertyMaster = {
  id: string;
  name: string;
  owner: string;
  ownerEntity: string;
  acquired: string;
  /** 7桁ハイフン付き（例: 462-0834） */
  postalCode: string;
  address: string;
  /** Notion「所有物件関係」DB_物件情報の鍵番号。null は「なし」。ライブ取得時は上書き */
  keyNumber: number | null;
  matchNames: string[];
  roomsExpected: number;
  managers: string[];
  loanIds: string[];
};

export const RE_PROPERTY_MASTER: RePropertyMaster[] = [
  {
    id: "grandole-i",
    name: "Grandole志賀本通Ⅰ",
    owner: "法人",
    ownerEntity: "リビングサポート松",
    acquired: "2025-02-28",
    postalCode: "462-0834",
    address: "愛知県名古屋市北区長田町4丁目69番地5",
    keyNumber: 2842,
    matchNames: [
      "Grandole志賀本通I",
      "02_Grandole志賀本通I",
      "Grandole志賀本通Ⅰ",
    ],
    roomsExpected: 8,
    managers: ["LEAF", "Tcell"],
    loanIds: ["orix-g1-corp"],
  },
  {
    id: "grandole-ii",
    name: "Grandole志賀本通Ⅱ",
    owner: "個人",
    ownerEntity: "松野真治",
    acquired: "2022-09",
    postalCode: "462-0834",
    address: "愛知県名古屋市北区長田町4丁目69番地5",
    keyNumber: 1555,
    matchNames: [
      "Grandole志賀本通II",
      "01_Grandole志賀本通II",
      "Grandole志賀本通Ⅱ",
    ],
    roomsExpected: 8,
    managers: ["ホームプランナー"],
    loanIds: ["orix-g2-pers"],
  },
  {
    id: "caramel",
    name: "キャラメル",
    owner: "個人",
    ownerEntity: "松野真治",
    acquired: "2025-12-26",
    postalCode: "459-8008",
    address: "愛知県名古屋市緑区文久山418",
    keyNumber: null,
    matchNames: ["キャラメル", "03_キャラメル"],
    roomsExpected: 4,
    managers: ["Tcell"],
    loanIds: ["shiga-caramel", "shiga-caramel-cost"],
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

/** Notion 行タイトルから物件 id。II を I より先に照合する */
export function matchPropertyIdByNotionName(name: string): string | null {
  const n = (name || "").trim();
  if (!n) return null;
  const isII =
    /志賀本通\s*II/i.test(n) ||
    /志賀本通Ⅱ/.test(n) ||
    /Grandole.*II/i.test(n);
  const order = ["grandole-ii", "grandole-i", "caramel"] as const;
  for (const id of order) {
    const info = RE_PROPERTY_MASTER.find((p) => p.id === id);
    if (!info) continue;
    const names = [info.name, ...info.matchNames];
    const hit = names.some((m) => n === m || n.includes(m) || m.includes(n));
    if (!hit) continue;
    if (id === "grandole-i" && isII) continue;
    if (id === "grandole-ii" && !isII) continue;
    return id;
  }
  return null;
}

/** YAML キャッシュの上に Notion 取得分を載せる */
export function applyLiveKeyNumbers(
  rows: RePropertyMaster[],
  keys: Record<string, number | null>
): RePropertyMaster[] {
  return rows.map((p) =>
    Object.prototype.hasOwnProperty.call(keys, p.id)
      ? { ...p, keyNumber: keys[p.id] ?? null }
      : p
  );
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
