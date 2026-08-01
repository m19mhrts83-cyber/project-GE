import { NOTION_TASK_LANES, type NotionLaneConfig } from "@/lib/notionTaskDbs";

export type { NotionLaneConfig };

export type NotionTask = {
  id: string;
  url: string;
  title: string;
  status: string;
  due: string | null;
  overdue: boolean;
};

export type NotionBoardSummary = {
  connected: boolean;
  reason?: string;
  boardUrl?: string;
  byStatus: Record<string, number>;
  overdue: NotionTask[];
  openSample: NotionTask[];
};

const NOTION_VERSION = "2022-06-28";

export function loadNotionLaneConfig(lane: string): NotionLaneConfig | null {
  return NOTION_TASK_LANES[lane] || null;
}

export function notionTokenConfigured(): boolean {
  return Boolean((process.env.NOTION_API_TOKEN || "").trim());
}

function headers(): HeadersInit {
  const token = (process.env.NOTION_API_TOKEN || "").trim();
  return {
    Authorization: `Bearer ${token}`,
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

function todayJst(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

export async function queryLaneBoard(lane: string): Promise<NotionBoardSummary> {
  const cfg = loadNotionLaneConfig(lane);
  if (!cfg) {
    return { connected: false, reason: "YAML未登録", byStatus: {}, overdue: [], openSample: [] };
  }
  if (!notionTokenConfigured()) {
    return {
      connected: false,
      reason: "NOTION_API_TOKEN 未設定",
      boardUrl: cfg.board_url,
      byStatus: {},
      overdue: [],
      openSample: [],
    };
  }

  const byStatus: Record<string, number> = {};
  const overdue: NotionTask[] = [];
  const openSample: NotionTask[] = [];
  const today = todayJst();
  let cursor: string | undefined;
  let pages = 0;

  try {
    do {
      const body: Record<string, unknown> = { page_size: 100 };
      if (cfg.due_prop) {
        body.sorts = [{ property: cfg.due_prop, direction: "ascending" }];
      }
      if (cursor) body.start_cursor = cursor;

      const res = await fetch(
        `https://api.notion.com/v1/databases/${cfg.database_id}/query`,
        {
          method: "POST",
          headers: headers(),
          body: JSON.stringify(body),
          next: { revalidate: 300 },
        },
      );
      if (!res.ok) {
        const text = await res.text();
        return {
          connected: false,
          reason: `Notion API ${res.status}: ${text.slice(0, 160)}`,
          boardUrl: cfg.board_url,
          byStatus: {},
          overdue: [],
          openSample: [],
        };
      }
      const data = (await res.json()) as {
        results: Array<{
          id: string;
          url: string;
          properties: Record<string, unknown>;
        }>;
        has_more: boolean;
        next_cursor: string | null;
      };
      for (const row of data.results) {
        const status = statusName(row.properties, cfg.status_prop) || "(なし)";
        byStatus[status] = (byStatus[status] || 0) + 1;
        const due = dateStart(row.properties, cfg.due_prop);
        const done = cfg.done_statuses.includes(status);
        const task: NotionTask = {
          id: row.id,
          url: row.url,
          title: richTitle(row.properties, cfg.title_prop),
          status,
          due,
          overdue: Boolean(due && !done && due < today),
        };
        if (task.overdue) overdue.push(task);
        if (!done && openSample.length < 8) openSample.push(task);
      }
      cursor = data.has_more ? data.next_cursor || undefined : undefined;
      pages += 1;
    } while (cursor && pages < 5);

    return {
      connected: true,
      boardUrl: cfg.board_url,
      byStatus,
      overdue,
      openSample,
    };
  } catch (e) {
    return {
      connected: false,
      reason: e instanceof Error ? e.message : String(e),
      boardUrl: cfg.board_url,
      byStatus: {},
      overdue: [],
      openSample: [],
    };
  }
}

export async function createNotionTask(
  lane: string,
  input: { title: string; summary?: string; due?: string | null },
): Promise<{ ok: true; url: string; id: string } | { ok: false; error: string }> {
  const cfg = loadNotionLaneConfig(lane);
  if (!cfg) return { ok: false, error: "YAML未登録" };
  if (!notionTokenConfigured()) {
    return { ok: false, error: "NOTION_API_TOKEN 未設定" };
  }

  const properties: Record<string, unknown> = {
    [cfg.title_prop]: {
      title: [{ type: "text", text: { content: input.title.slice(0, 200) } }],
    },
    [cfg.status_prop]: {
      status: { name: cfg.initial_status },
    },
  };
  if (cfg.due_prop && input.due) {
    properties[cfg.due_prop] = { date: { start: input.due.slice(0, 10) } };
  }
  if (cfg.start_prop) {
    properties[cfg.start_prop] = { date: { start: todayJst() } };
  }

  const children = input.summary
    ? [
        {
          object: "block",
          type: "paragraph",
          paragraph: {
            rich_text: [
              {
                type: "text",
                text: { content: input.summary.slice(0, 1800) },
              },
            ],
          },
        },
      ]
    : [];

  const res = await fetch("https://api.notion.com/v1/pages", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({
      parent: { database_id: cfg.database_id },
      properties,
      children,
    }),
  });
  if (!res.ok) {
    const text = await res.text();
    return { ok: false, error: `${res.status}: ${text.slice(0, 240)}` };
  }
  const data = (await res.json()) as { id: string; url: string };
  return { ok: true, id: data.id, url: data.url };
}
