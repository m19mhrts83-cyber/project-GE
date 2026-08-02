/** 物件メタ（管理会社・鍵番号）。正本写し: config/property_info.yaml */

export type PropertyRoomInfo = {
  manager?: string;
};

export type PropertyInfo = {
  name: string;
  short?: string;
  match_names: string[];
  managers: string[];
  key_number: number | null;
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
      match_names: [
        "Grandole志賀本通I",
        "02_Grandole志賀本通I",
        "Grandole志賀本通Ⅰ",
      ],
      managers: ["LEAF", "Tcell"],
      key_number: 2842,
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
      match_names: [
        "Grandole志賀本通II",
        "01_Grandole志賀本通II",
        "Grandole志賀本通Ⅱ",
      ],
      managers: ["ホームプランナー"],
      key_number: 1555,
      rooms: {
        "102": { manager: "ホームプランナー" },
        "205": { manager: "ホームプランナー" },
      },
    },
    caramel: {
      name: "キャラメル",
      short: "C",
      match_names: ["キャラメル", "03_キャラメル"],
      managers: ["Tcell"],
      key_number: null,
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

/** 号室メモや YAML から管理会社を解決 */
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
  return null;
}

/** 棟の管理会社一覧（YAML ＋ 号室から推定した分をマージ） */
export function managersForProperty(
  propertyId: string,
  roomNotes: { room: string; note?: string | null }[],
): string[] {
  const info = getPropertyInfo(propertyId);
  const set = new Set<string>(info?.managers || []);
  for (const r of roomNotes) {
    const m = resolveRoomManager(propertyId, r.room, r.note);
    if (m) set.add(m);
  }
  return [...set];
}

export function fmtKeyNumber(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return String(n);
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
