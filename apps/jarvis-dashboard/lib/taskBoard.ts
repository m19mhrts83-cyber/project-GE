/**
 * タスク看板バックエンド切替。
 * JARVIS_TASK_BACKEND=todoist|notion（既定: todoist）
 */
import {
  createNotionTask,
  loadNotionLaneConfig,
  queryLaneBoard as queryNotionLaneBoard,
  updateNotionTaskStatus,
  type NotionBoardSummary,
} from "@/lib/notionTasks";
import {
  createTodoistTask,
  queryTodoistLaneBoard,
  updateTodoistTaskStatus,
} from "@/lib/todoistTasks";

export type TaskBackend = "todoist" | "notion";

export function getTaskBackend(): TaskBackend {
  const raw = (process.env.JARVIS_TASK_BACKEND || "todoist").trim().toLowerCase();
  return raw === "notion" ? "notion" : "todoist";
}

export async function queryTaskLaneBoard(
  lane: string,
): Promise<NotionBoardSummary & { backend: TaskBackend }> {
  const backend = getTaskBackend();
  const board =
    backend === "notion"
      ? await queryNotionLaneBoard(lane)
      : await queryTodoistLaneBoard(lane);
  return { ...board, backend };
}

export async function updateTaskStatus(
  lane: string,
  taskId: string,
  status: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  if (getTaskBackend() === "notion") {
    return updateNotionTaskStatus(lane, taskId, status);
  }
  return updateTodoistTaskStatus(lane, taskId, status);
}

export async function createTask(
  lane: string,
  input: {
    title: string;
    summary?: string;
    due?: string | null;
    propertyName?: string | null;
  },
): Promise<{ ok: true; url: string; id: string } | { ok: false; error: string }> {
  if (getTaskBackend() === "notion") {
    return createNotionTask(lane, input);
  }
  // Todoist 側に物件サブグループは無い（ラベル運用）。propertyName は description 先頭に残す。
  let summary = input.summary || "";
  if (input.propertyName?.trim()) {
    summary = `物件: ${input.propertyName.trim()}\n${summary}`.trim();
  }
  return createTodoistTask(lane, {
    title: input.title,
    summary: summary || undefined,
    due: input.due,
  });
}

/** promote 時の物件名必須チェック（Notion のみ） */
export function laneRequiresPropertyName(lane: string): boolean {
  if (getTaskBackend() !== "notion") return false;
  const cfg = loadNotionLaneConfig(lane);
  return Boolean(cfg?.property_prop);
}
