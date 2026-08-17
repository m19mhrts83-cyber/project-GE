/** 物件メタ（管理会社・鍵番号）。正本写し: config/property_info.yaml */

export type PropertyRoomInfo = {
  manager?: string;
};

export type PropertyInfo = {
  name: string;
  short?: string;
  /** 個人 / 法人 */
  owner?: string;
  owner_entity?: string;
  acquired?: string;
  /** 7桁ハイフン付き（例: 462-0834） */
  postal_code?: string;
  /** 物件所在地（棟単位） */
  address?: string;
  match_names: string[];
  managers: string[];
  /** 号室・メモで特定できないときの既定管理会社 */
  default_manager?: string;
  key_number: number | null;
  /** 借入残高トラッカー id（任意） */
  loan_ids?: string[];
  rooms: Record<string, PropertyRoomInfo>;
};

export type PropertyInfoCatalog = {
  notion: {
    database_id: string;
    data_source_id?: string;
    board_url: string;
    title_prop: string;
    key_prop: string;
  };
  properties: Record<string, PropertyInfo>;
};

/** YAML の写し（ビルド同梱）。Notion API 成功時は key_number だけ上書き */
export const PROPERTY_INFO: PropertyInfoCatalog = {
  notion: {
    database_id: "2e5f6bbe5a76801595f2c1bb8a5d23e7",
    data_source_id: "2e5f6bbe-5a76-8021-9ea6-000b237b925c",
    board_url:
      "https://app.notion.com/p/2e5f6bbe5a76801595f2c1bb8a5d23e7?v=2e5f6bbe5a7680d9a4d1000c2111cd0c",
    title_prop: "名前",
    key_prop: "鍵番号",
  },
  properties: {
    "grandole-i": {
      name: "Grandole志賀本通I",
      short: "I",
      owner: "法人",
      owner_entity: "リビングサポート松",
      acquired: "2025-02-28",
      postal_code: "462-0834",
      address: "愛知県名古屋市北区長田町4丁目69番地5",
      match_names: [
        "Grandole志賀本通I",
        "02_Grandole志賀本通I",
        "Grandole志賀本通Ⅰ",
      ],
      managers: ["LEAF", "Tcell"],
      default_manager: "ミニテック",
      key_number: 2842,
      loan_ids: ["orix-g1-corp"],
      rooms: {
        "102": { manager: "Tcell" },
        "105": { manager: "LEAF" },
        "201": { manager: "ミニテック" },
        "202": { manager: "LEAF" },
      },
    },
    "grandole-ii": {
      name: "Grandole志賀本通II",
      short: "II",
      owner: "個人",
      owner_entity: "松野真治",
      acquired: "2022-09",
      postal_code: "462-0834",
      address: "愛知県名古屋市北区長田町4丁目69番地5",
      match_names: [
        "Grandole志賀本通II",
        "01_Grandole志賀本通II",
        "Grandole志賀本通Ⅱ",
      ],
      managers: ["ホームプランナー"],
      key_number: 1555,
      loan_ids: ["orix-g2-pers"],
      rooms: {},
    },
    caramel: {
      name: "キャラメル",
      short: "C",
      owner: "個人",
      owner_entity: "松野真治",
      acquired: "2025-12-26",
      postal_code: "459-8008",
      address: "愛知県名古屋市緑区文久山418",
      match_names: ["キャラメル", "03_キャラメル"],
      managers: ["Tcell"],
      key_number: null,
      loan_ids: ["shiga-caramel", "shiga-caramel-cost"],
      rooms: {},
    },
  },
};

const NOTE_MANAGER_RE =
  /\b(LEAF|Leaf|leaf|Tcell|TCELL|ミニテック|ホームプランナー)\b/;

function normalizeManager(raw: string): string {
  const s = raw.trim();
  if (/^leaf$/i.test(s)) return "LEAF";
  if (/^tcell$/i.test(s)) return "Tcell";
  return s;
}

export function getPropertyInfo(propertyId: string): PropertyInfo | null {
  return PROPERTY_INFO.properties[propertyId] || null;
}

/** 号室メモや YAML から管理会社を解決。
 * 優先: 号室指定 → メモ推定 → default_manager → 棟が1社のみならその社。
 */
export function resolveRoomManager(
  propertyId: string,
  room: string,
  note?: string | null,
): string | null {
  const info = getPropertyInfo(propertyId);
  const fromYaml = info?.rooms?.[room]?.manager;
  if (fromYaml) return fromYaml;
  const m = (note || "").match(NOTE_MANAGER_RE);
  if (m?.[1]) return normalizeManager(m[1]);
  if (info?.default_manager) return info.default_manager;
  if (info?.managers?.length === 1) return info.managers[0];
  return null;
}

/** 棟の管理会社一覧（YAML ＋ 号室から推定した分をマージ） */
export function managersForProperty(
  propertyId: string,
  roomNotes: { room: string; note?: string | null }[],
): string[] {
  const info = getPropertyInfo(propertyId);
  const set = new Set<string>(info?.managers || []);
  if (info?.default_manager) set.add(info.default_manager);
  for (const r of roomNotes) {
    const m = resolveRoomManager(propertyId, r.room, r.note);
    if (m) set.add(m);
  }
  return [...set];
}

export function fmtKeyNumber(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "なし";
  return String(n);
}

export function fmtPostalCode(code: string | null | undefined): string {
  const raw = (code || "").trim();
  if (!raw) return "";
  const digits = raw.replace(/\D/g, "");
  if (digits.length === 7) return `〒${digits.slice(0, 3)}-${digits.slice(3)}`;
  if (raw.startsWith("〒")) return raw;
  return `〒${raw}`;
}

export function matchPropertyIdByNotionName(name: string): string | null {
  const n = (name || "").trim();
  if (!n) return null;
  // II を I より先に照合（「…I」が「…II」に部分一致するのを防ぐ）
  const order = ["grandole-ii", "grandole-i", "caramel"];
  for (const id of order) {
    const info = PROPERTY_INFO.properties[id];
    if (!info) continue;
    const hit = info.match_names.some(
      (m) => n === m || n.includes(m) || m.includes(n),
    );
    if (!hit && !(n.includes(info.name) || info.name.includes(n))) continue;
    if (
      id === "grandole-i" &&
      (/志賀本通\s*II/i.test(n) || /志賀本通Ⅱ/.test(n) || /Grandole.*II/i.test(n))
    ) {
      continue;
    }
    return id;
  }
  return null;
}
