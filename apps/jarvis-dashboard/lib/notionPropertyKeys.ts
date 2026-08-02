import {
  PROPERTY_INFO,
  matchPropertyIdByNotionName,
  type PropertyInfoCatalog,
} from "@/lib/propertyInfo";

export type PropertyKeysResult = {
  connected: boolean;
  reason?: string;
  boardUrl: string;
  /** property_id → 鍵番号（Notion 優先、失敗時は YAML キャッシュ） */
  keys: Record<string, number | null>;
  source: "notion" | "yaml_cache";
};

const NOTION_VERSION = "2022-06-28";

function notionToken(): string {
  return (process.env.NOTION_API_TOKEN || "").trim();
}

function richTitle(
  props: Record<string, unknown>,
  titleProp: string,
): string {
  const p = props[titleProp] as
    | { title?: Array<{ plain_text?: string }> }
    | undefined;
  return (p?.title || []).map((t) => t.plain_text || "").join("").trim();
}

function numberProp(
  props: Record<string, unknown>,
  keyProp: string,
): number | null {
  const p = props[keyProp] as { number?: number | null } | undefined;
  const n = p?.number;
  return typeof n === "number" && !Number.isNaN(n) ? n : null;
}

function yamlKeys(): Record<string, number | null> {
  const out: Record<string, number | null> = {};
  for (const [id, info] of Object.entries(PROPERTY_INFO.properties)) {
    out[id] = info.key_number;
  }
  return out;
}

/** Notion DB_物件情報 から鍵番号を取得。未共有時は YAML キャッシュ */
export async function fetchPropertyKeyNumbers(
  catalog: PropertyInfoCatalog = PROPERTY_INFO,
): Promise<PropertyKeysResult> {
  const boardUrl = catalog.notion.board_url;
  const cached = yamlKeys();
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

  const dbId = catalog.notion.database_id.replace(/-/g, "");
  const dashed = `${dbId.slice(0, 8)}-${dbId.slice(8, 12)}-${dbId.slice(12, 16)}-${dbId.slice(16, 20)}-${dbId.slice(20)}`;

  try {
    const keys = { ...cached };
    let cursor: string | undefined;
    let pages = 0;
    do {
      const res = await fetch(`https://api.notion.com/v1/databases/${dashed}/query`, {
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
      });
      if (!res.ok) {
        const body = await res.text();
        return {
          connected: false,
          reason:
            res.status === 404
              ? "Notion DB 未共有（Jarvisダッシュボード Integration に接続してください）"
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
        const name = richTitle(props, catalog.notion.title_prop);
        const key = numberProp(props, catalog.notion.key_prop);
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
