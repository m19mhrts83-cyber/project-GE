import {
  KURASHIFT_NOTION_LANES,
  type NotionLaneConfig,
} from "@/lib/notionTaskDbs";

export type NotionTask = {
  id: string;
  url: string;
  title: string;
  status: string;
  due: string | null;
};

export type NotionLaneBoard = {
  lane: string;
  title: string;
  connected: boolean;
  reason?: string;
  boardUrl: string;
  open: NotionTask[];
};

const NOTION_VERSION = "2022-06-28";

function token(): string {
  return (process.env.NOTION_API_TOKEN || "").trim();
}

function headers(): HeadersInit {
  return {
    Authorization: `Bearer ${token()}`,
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
  };
}

function richTitle(props: Record<string, unknown>, titleProp: string): string {
  const p = props[titleProp] as
    | { title?: Array<{ plain_text?: string }> }
    | undefined;
  return (p?.title || []).map((t) => t.plain_text || "").join("").trim() || "(無題)";
}

function statusName(props: Record<string, unknown>, statusProp: string): string {
  const p = props[statusProp] as
    | { status?: { name?: string }; select?: { name?: string } }
    | undefined;
  return p?.status?.name || p?.select?.name || "";
}

function dateStart(props: Record<string, unknown>, dueProp: string | null): string | null {
  if (!dueProp) return null;
  const p = props[dueProp] as { date?: { start?: string } } | undefined;
  const s = p?.date?.start;
  return s ? s.slice(0, 10) : null;
}

async function queryLane(lane: string, cfg: NotionLaneConfig): Promise<NotionLaneBoard> {
  if (!token()) {
    return {
      lane,
      title: cfg.title,
      connected: false,
      reason: "NOTION_API_TOKEN 未設定",
      boardUrl: cfg.board_url,
      open: [],
    };
  }
  const res = await fetch(`https://api.notion.com/v1/databases/${cfg.database_id}/query`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ page_size: 40 }),
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    return {
      lane,
      title: cfg.title,
      connected: false,
      reason: `${res.status}: ${text.slice(0, 160)}`,
      boardUrl: cfg.board_url,
      open: [],
    };
  }
  const data = (await res.json()) as {
    results?: Array<{
      id: string;
      url: string;
      properties?: Record<string, unknown>;
    }>;
  };
  const open: NotionTask[] = [];
  for (const row of data.results || []) {
    const props = row.properties || {};
    const status = statusName(props, cfg.status_prop);
    if (cfg.done_statuses.includes(status)) continue;
    open.push({
      id: row.id,
      url: row.url,
      title: richTitle(props, cfg.title_prop),
      status,
      due: dateStart(props, cfg.due_prop),
    });
  }
  return {
    lane,
    title: cfg.title,
    connected: true,
    boardUrl: cfg.board_url,
    open,
  };
}

export async function queryKurashiftNotionBoards(): Promise<NotionLaneBoard[]> {
  const ids = ["properties", "kodate", "kazoku"] as const;
  return Promise.all(ids.map((id) => queryLane(id, KURASHIFT_NOTION_LANES[id])));
}

export function notionTokenConfigured(): boolean {
  return Boolean(token());
}
