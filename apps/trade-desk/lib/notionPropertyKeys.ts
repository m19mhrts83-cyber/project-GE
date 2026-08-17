/**
 * Notion「所有物件関係」DB_物件情報から鍵番号を取得。
 * 正本: config/property_info.yaml の notion.* 。トークン未設定・失敗時は YAML キャッシュ。
 */
import {
  RE_PROPERTY_MASTER,
  matchPropertyIdByNotionName,
} from "./rePropertyMaster";

export const NOTION_PROPERTY_DB = {
  database_id: "2e5f6bbe5a76801595f2c1bb8a5d23e7",
  data_source_id: "2e5f6bbe-5a76-8021-9ea6-000b237b925c",
  board_url:
    "https://app.notion.com/p/2e5f6bbe5a76801595f2c1bb8a5d23e7?v=2e5f6bbe5a7680d9a4d1000c2111cd0c",
  title_prop: "名前",
  key_prop: "鍵番号",
};

export type PropertyKeysResult = {
  connected: boolean;
  reason?: string;
  boardUrl: string;
  keys: Record<string, number | null>;
  source: "notion" | "yaml_cache";
};

const NOTION_VERSION = "2022-06-28";

export function notionToken(): string {
  return (process.env.NOTION_API_TOKEN || "").trim();
}

function richTitle(
  props: Record<string, unknown>,
  titleProp: string
): string {
  const p = props[titleProp] as
    | { title?: Array<{ plain_text?: string }> }
    | undefined;
  return (p?.title || []).map((t) => t.plain_text || "").join("").trim();
}

const NONE_KEY = /^(なし|無し|-|—|–)$/;

/** number / rich_text / select / formula から鍵番号。空・「なし」は null */
export function parseKeyNumberValue(prop: unknown): number | null {
  if (!prop || typeof prop !== "object") return null;
  const p = prop as Record<string, unknown>;
  if (typeof p.number === "number" && Number.isFinite(p.number)) return p.number;
  const formula = p.formula as { number?: number | null } | undefined;
  if (typeof formula?.number === "number" && Number.isFinite(formula.number)) {
    return formula.number;
  }
  const texts: string[] = [];
  for (const key of ["rich_text", "title"] as const) {
    const arr = p[key];
    if (Array.isArray(arr)) {
      texts.push(
        arr.map((t: { plain_text?: string }) => t.plain_text || "").join("")
      );
    }
  }
  const sel = p.select as { name?: string } | null | undefined;
  if (sel?.name) texts.push(sel.name);
  const raw = texts.join("").trim();
  if (!raw || NONE_KEY.test(raw)) return null;
  const n = Number(String(raw).replace(/[^\d.-]/g, ""));
  return Number.isFinite(n) ? n : null;
}

export function yamlKeyCache(): Record<string, number | null> {
  const out: Record<string, number | null> = {};
  for (const p of RE_PROPERTY_MASTER) out[p.id] = p.keyNumber;
  return out;
}

function dashedDatabaseId(raw: string): string {
  const dbId = raw.replace(/-/g, "");
  return `${dbId.slice(0, 8)}-${dbId.slice(8, 12)}-${dbId.slice(12, 16)}-${dbId.slice(16, 20)}-${dbId.slice(20)}`;
}

/** Notion DB_物件情報 から鍵番号を取得。未設定・失敗時は YAML キャッシュ */
export async function fetchPropertyKeyNumbers(): Promise<PropertyKeysResult> {
  const boardUrl = NOTION_PROPERTY_DB.board_url;
  const cached = yamlKeyCache();
  const token = notionToken();
  if (!token) {
    return {
      connected: false,
      reason: "NOTION_API_TOKEN 未設定",
      boardUrl,
      keys: cached,
      source: "yaml_cache",
    };
  }

  const dashed = dashedDatabaseId(NOTION_PROPERTY_DB.database_id);

  try {
    const keys = { ...cached };
    let cursor: string | undefined;
    let pages = 0;
    do {
      const res = await fetch(
        `https://api.notion.com/v1/databases/${dashed}/query`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            start_cursor: cursor,
            page_size: 50,
          }),
          next: { revalidate: 300 },
        }
      );
      if (!res.ok) {
        const body = await res.text();
        return {
          connected: false,
          reason:
            res.status === 404
              ? "Notion DB 未共有（Integration に DB_物件情報を接続してください）"
              : `Notion API ${res.status}: ${body.slice(0, 120)}`,
          boardUrl,
          keys: cached,
          source: "yaml_cache",
        };
      }
      const data = (await res.json()) as {
        results?: Array<{ properties?: Record<string, unknown> }>;
        has_more?: boolean;
        next_cursor?: string | null;
      };
      for (const row of data.results || []) {
        const props = row.properties || {};
        const name = richTitle(props, NOTION_PROPERTY_DB.title_prop);
        const key = parseKeyNumberValue(props[NOTION_PROPERTY_DB.key_prop]);
        const pid = matchPropertyIdByNotionName(name);
        if (pid) keys[pid] = key;
      }
      cursor = data.has_more ? data.next_cursor || undefined : undefined;
      pages += 1;
    } while (cursor && pages < 5);

    return {
      connected: true,
      boardUrl,
      keys,
      source: "notion",
    };
  } catch (e) {
    return {
      connected: false,
      reason: e instanceof Error ? e.message : String(e),
      boardUrl,
      keys: cached,
      source: "yaml_cache",
    };
  }
}
