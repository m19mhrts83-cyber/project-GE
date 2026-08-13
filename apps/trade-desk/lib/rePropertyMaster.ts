/** ③-C 物件マスタ最小揃え（写し）。正本: config/kurashift_re_property_master.yaml */

export type RePropertyMaster = {
  id: string;
  name: string;
  owner: string;
  ownerEntity: string;
  acquired: string;
  address: string;
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
    address: "愛知県名古屋市北区長田町4丁目69番地5",
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
    address: "愛知県名古屋市北区長田町4丁目69番地5",
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
    address: "愛知県名古屋市緑区文久山418",
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
