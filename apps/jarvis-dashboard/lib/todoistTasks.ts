import {
  loadTodoistLaneConfig,
  type TodoistLaneConfig,
} from "@/lib/todoistProjects";
import type { NotionBoardSummary, NotionTask } from "@/lib/notionTasks";

const API = "https://api.todoist.com/api/v1";
const MAX_TASKS_PER_COL = 40;

export function todoistTokenConfigured(): boolean {
  return Boolean((process.env.TODOIST_API_TOKEN || "").trim());
}

function token(): string {
  return (process.env.TODOIST_API_TOKEN || "").trim();
}

function headers(): HeadersInit {
  return {
    Authorization: `Bearer ${token()}`,
    "Content-Type": "application/json",
  };
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

type TodoistTaskRow = {
  id?: string;
  content?: string;
  description?: string;
  url?: string;
  section_id?: string | null;
  labels?: string[];
  due?: { date?: string } | null;
  is_completed?: boolean;
};

async function fetchProjectTasks(projectId: string): Promise<TodoistTaskRow[]> {
  const out: TodoistTaskRow[] = [];
  let cursor: string | undefined;
  let pages = 0;
  do {
    const qs = new URLSearchParams({ project_id: projectId });
    if (cursor) qs.set("cursor", cursor);
    const res = await fetch(`${API}/tasks?${qs.toString()}`, {
      headers: headers(),
      next: { revalidate: 60 },
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`Todoist API ${res.status}: ${text.slice(0, 160)}`);
    }
    const data = (await res.json()) as
      | TodoistTaskRow[]
      | { results?: TodoistTaskRow[]; next_cursor?: string | null };
    if (Array.isArray(data)) {
      out.push(...data);
      break;
    }
    out.push(...(data.results || []));
    cursor = data.next_cursor || undefined;
    pages += 1;
  } while (cursor && pages < 8);
  return out;
}

function columnMeta(cfg: TodoistLaneConfig) {
  const hideDone = Boolean(cfg.hideDoneOnBoard);
  const columnOrder = hideDone
    ? [...cfg.openSections]
    : [
        ...cfg.openSections,
        ...cfg.doneSections.filter((s) => !cfg.openSections.includes(s)),
      ];
  const moveStatuses = [
    ...cfg.openSections,
    ...cfg.doneSections.filter((s) => !cfg.openSections.includes(s)),
  ];
  return { hideDone, columnOrder, moveStatuses };
}

export async function queryTodoistLaneBoard(
  lane: string,
): Promise<NotionBoardSummary> {
  const cfg = loadTodoistLaneConfig(lane);
  if (!cfg) return emptyBoard({ reason: "Todoist YAML未登録" });
  const { hideDone, columnOrder, moveStatuses } = columnMeta(cfg);

  if (!todoistTokenConfigured()) {
    return emptyBoard({
      reason: "TODOIST_API_TOKEN 未設定",
      boardUrl: cfg.boardUrl,
      openStatuses: cfg.openSections,
      columnOrder,
      moveStatuses,
    });
  }

  const sidToName = Object.fromEntries(
    Object.entries(cfg.sectionIds).map(([name, id]) => [id, name]),
  );

  try {
    const rows = await fetchProjectTasks(cfg.projectId);
    const byStatus: Record<string, number> = {};
    const columns: Record<string, NotionTask[]> = {};
    const overdue: NotionTask[] = [];
    const openSample: NotionTask[] = [];
    const today = todayJst();

    for (const row of rows) {
      if (row.is_completed) continue;
      const labels = (row.labels || []).map(String);
      if (cfg.filterByLaneLabel && !labels.includes(cfg.laneLabel)) continue;

      const status =
        sidToName[String(row.section_id || "")] || "(なし)";
      const done = cfg.doneSections.includes(status);
      if (hideDone && done) continue;

      byStatus[status] = (byStatus[status] || 0) + 1;
      const due = row.due?.date ? row.due.date.slice(0, 10) : null;
      const task: NotionTask = {
        id: String(row.id || ""),
        url:
          row.url ||
          `https://app.todoist.com/app/task/${encodeURIComponent(String(row.id || ""))}`,
        title: (row.content || "").trim() || "(無題)",
        status,
        due,
        overdue: Boolean(due && !done && due < today),
      };
      if (!task.id) continue;
      if (task.overdue) overdue.push(task);
      if (!done && openSample.length < 8) openSample.push(task);
      if (!columnOrder.includes(status) && hideDone) continue;
      const col = columns[status] || (columns[status] = []);
      if (col.length < MAX_TASKS_PER_COL) col.push(task);
    }

    const orderedColumns: Record<string, NotionTask[]> = {};
    for (const s of columnOrder) orderedColumns[s] = columns[s] || [];
    for (const [k, v] of Object.entries(columns)) {
      if (!(k in orderedColumns)) orderedColumns[k] = v;
    }
    const boardByStatus: Record<string, number> = {};
    for (const s of columnOrder) {
      boardByStatus[s] = (orderedColumns[s] || []).length;
    }

    return {
      connected: true,
      boardUrl: cfg.boardUrl,
      lane,
      openStatuses: cfg.openSections,
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
      boardUrl: cfg.boardUrl,
      openStatuses: cfg.openSections,
      columnOrder,
      moveStatuses,
    });
  }
}

export async function createTodoistTask(
  lane: string,
  input: {
    title: string;
    summary?: string;
    due?: string | null;
  },
): Promise<{ ok: true; url: string; id: string } | { ok: false; error: string }> {
  const cfg = loadTodoistLaneConfig(lane);
  if (!cfg) return { ok: false, error: "Todoist レーン未登録" };
  if (!todoistTokenConfigured()) {
    return { ok: false, error: "TODOIST_API_TOKEN 未設定" };
  }
  const sectionId = cfg.sectionIds[cfg.initialSection];
  if (!sectionId) return { ok: false, error: "初期セクション未設定" };

  const body: Record<string, unknown> = {
    content: input.title.slice(0, 500),
    project_id: cfg.projectId,
    section_id: sectionId,
    labels: [cfg.laneLabel],
  };
  if (input.summary?.trim()) {
    body.description = input.summary.trim().slice(0, 16000);
  }
  if (input.due?.trim()) {
    body.due_date = input.due.trim().slice(0, 10);
  }

  const res = await fetch(`${API}/tasks`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    return { ok: false, error: `${res.status}: ${text.slice(0, 240)}` };
  }
  const data = (await res.json()) as { id?: string; url?: string };
  const id = String(data.id || "");
  const url =
    data.url ||
    `https://app.todoist.com/app/task/${encodeURIComponent(id)}`;
  return { ok: true, id, url };
}

export async function updateTodoistTaskStatus(
  lane: string,
  taskId: string,
  status: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  const cfg = loadTodoistLaneConfig(lane);
  if (!cfg) return { ok: false, error: "Todoist レーン未登録" };
  if (!todoistTokenConfigured()) {
    return { ok: false, error: "TODOIST_API_TOKEN 未設定" };
  }
  const allowed = [...cfg.openSections, ...cfg.doneSections];
  if (!allowed.includes(status)) {
    return { ok: false, error: `未対応のステータス: ${status}` };
  }
  const sectionId = cfg.sectionIds[status];
  if (!sectionId) return { ok: false, error: `section_id なし: ${status}` };

  const res = await fetch(
    `${API}/tasks/${encodeURIComponent(taskId)}/move`,
    {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ section_id: sectionId }),
    },
  );
  if (!res.ok && res.status !== 204) {
    const text = await res.text();
    return { ok: false, error: `${res.status}: ${text.slice(0, 240)}` };
  }
  return { ok: true };
}
