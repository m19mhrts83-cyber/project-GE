import {
  NOTION_TASK_LANES,
  type NotionLaneConfig,
} from "@/lib/notionTaskDbs";

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
  lane?: string;
  openStatuses: string[];
  /** open + done（完了は末尾）。UI 列順の正 */
  columnOrder: string[];
  /** 移動セレクト用（open + done） */
  moveStatuses: string[];
  byStatus: Record<string, number>;
  /** ステータス別タスク（列内スクロール前提で多めに保持） */
  columns: Record<string, NotionTask[]>;
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

function emptyBoard(
  partial: Partial<NotionBoardSummary> & { reason?: string },
): NotionBoardSummary {
  return {
    connected: false,
    openStatuses: [],
    columnOrder: [],
    moveStatuses: [],
    byStatus: {},
    columns: {},
    overdue: [],
    openSample: [],
    ...partial,
  };
}

const MAX_TASKS_PER_COL = 40;

export async function queryLaneBoard(lane: string): Promise<NotionBoardSummary> {
  const cfg = loadNotionLaneConfig(lane);
  if (!cfg) {
    return emptyBoard({ reason: "YAML未登録" });
  }
  const hideDone = Boolean(cfg.hide_done_on_board);
  const columnOrder = hideDone
    ? [...cfg.open_statuses]
    : [
        ...cfg.open_statuses,
        ...cfg.done_statuses.filter((s) => !cfg.open_statuses.includes(s)),
      ];
  const moveStatuses = [
    ...cfg.open_statuses,
    ...cfg.done_statuses.filter((s) => !cfg.open_statuses.includes(s)),
  ];

  if (!notionTokenConfigured()) {
    return emptyBoard({
      reason: "NOTION_API_TOKEN 未設定",
      boardUrl: cfg.board_url,
      openStatuses: cfg.open_statuses,
      columnOrder,
      moveStatuses,
    });
  }

  const byStatus: Record<string, number> = {};
  const columns: Record<string, NotionTask[]> = {};
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
        return emptyBoard({
          reason: `Notion API ${res.status}: ${text.slice(0, 160)}`,
          boardUrl: cfg.board_url,
          openStatuses: cfg.open_statuses,
          columnOrder,
          moveStatuses,
        });
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
        if (hideDone && done) continue;
        if (!columnOrder.includes(status) && hideDone) continue;
        const col = columns[status] || (columns[status] = []);
        if (col.length < MAX_TASKS_PER_COL) col.push(task);
      }
      cursor = data.has_more ? data.next_cursor || undefined : undefined;
      pages += 1;
    } while (cursor && pages < 5);

    const orderedColumns: Record<string, NotionTask[]> = {};
    for (const s of columnOrder) {
      orderedColumns[s] = columns[s] || [];
    }
    for (const [k, v] of Object.entries(columns)) {
      if (!(k in orderedColumns)) orderedColumns[k] = v;
    }

    const boardByStatus: Record<string, number> = {};
    for (const s of columnOrder) {
      boardByStatus[s] = (orderedColumns[s] || []).length;
    }

    return {
      connected: true,
      boardUrl: cfg.board_url,
      lane,
      openStatuses: cfg.open_statuses,
      columnOrder,
      moveStatuses,
      byStatus: hideDone ? boardByStatus : byStatus,
      columns: orderedColumns,
      overdue,
      openSample,
    };
  } catch (e) {
    return emptyBoard({
      reason: e instanceof Error ? e.message : String(e),
      boardUrl: cfg.board_url,
      openStatuses: cfg.open_statuses,
      columnOrder,
      moveStatuses,
    });
  }
}

/** Notion DB の物件名 select 選択肢を取得 */
export async function listPropertySelectOptions(
  lane: string,
): Promise<{ ok: true; options: string[] } | { ok: false; error: string }> {
  const cfg = loadNotionLaneConfig(lane);
  if (!cfg?.property_prop) {
    return { ok: true, options: [] };
  }
  if (!notionTokenConfigured()) {
    return { ok: false, error: "NOTION_API_TOKEN 未設定" };
  }
  const res = await fetch(
    `https://api.notion.com/v1/databases/${cfg.database_id}`,
    { headers: headers(), next: { revalidate: 600 } },
  );
  if (!res.ok) {
    const text = await res.text();
    return { ok: false, error: `${res.status}: ${text.slice(0, 200)}` };
  }
  const data = (await res.json()) as {
    properties?: Record<
      string,
      { type?: string; select?: { options?: { name?: string }[] } }
    >;
  };
  const prop = data.properties?.[cfg.property_prop];
  const options = (prop?.select?.options || [])
    .map((o) => (o.name || "").trim())
    .filter(Boolean);
  return { ok: true, options };
}

export async function createNotionTask(
  lane: string,
  input: {
    title: string;
    summary?: string;
    due?: string | null;
    propertyName?: string | null;
  },
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
  if (cfg.property_prop && input.propertyName?.trim()) {
    properties[cfg.property_prop] = {
      select: { name: input.propertyName.trim() },
    };
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

/** 看板から Notion ステータスを更新（片方向） */
export async function updateNotionTaskStatus(
  lane: string,
  pageId: string,
  status: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  const cfg = loadNotionLaneConfig(lane);
  if (!cfg) return { ok: false, error: "YAML未登録" };
  if (!notionTokenConfigured()) {
    return { ok: false, error: "NOTION_API_TOKEN 未設定" };
  }
  const allowed = [...cfg.open_statuses, ...cfg.done_statuses];
  if (!allowed.includes(status)) {
    return { ok: false, error: `未対応のステータス: ${status}` };
  }
  const res = await fetch(`https://api.notion.com/v1/pages/${pageId}`, {
    method: "PATCH",
    headers: headers(),
    body: JSON.stringify({
      properties: {
        [cfg.status_prop]: { status: { name: status } },
      },
    }),
  });
  if (!res.ok) {
    const text = await res.text();
    return { ok: false, error: `${res.status}: ${text.slice(0, 240)}` };
  }
  return { ok: true };
}
