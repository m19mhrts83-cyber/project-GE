"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { updateNotionTaskStatusAction } from "@/app/actions/notionBoard";
import type { NotionTask } from "@/lib/notionTasks";

type DragPayload = { id: string; from: string };

export default function NotionBoardClient({
  lane,
  path,
  openStatuses,
  columnOrder,
  moveStatuses,
  columns,
}: {
  lane: string;
  path: string;
  openStatuses: string[];
  columnOrder: string[];
  moveStatuses: string[];
  columns: Record<string, NotionTask[]>;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [err, setErr] = useState<string | null>(null);
  const [localCols, setLocalCols] = useState(columns);
  const [dragOver, setDragOver] = useState<string | null>(null);
  const [draggingId, setDraggingId] = useState<string | null>(null);

  useEffect(() => {
    setLocalCols(columns);
  }, [columns]);

  const order =
    columnOrder.length > 0 ? columnOrder : Object.keys(localCols);
  const statusChoices =
    moveStatuses.length > 0
      ? moveStatuses
      : openStatuses.length > 0
        ? openStatuses
        : order;

  function moveLocal(taskId: string, from: string, to: string) {
    if (from === to) return;
    setLocalCols((prev) => {
      const next: Record<string, NotionTask[]> = {};
      for (const k of Object.keys(prev)) next[k] = [...(prev[k] || [])];
      const fromList = next[from] || [];
      const idx = fromList.findIndex((t) => t.id === taskId);
      if (idx < 0) return prev;
      const [task] = fromList.splice(idx, 1);
      next[from] = fromList;
      next[to] = [...(next[to] || []), { ...task, status: to }];
      return next;
    });
  }

  function onStatusChange(pageId: string, status: string, fromStatus?: string) {
    const from =
      fromStatus ||
      Object.keys(localCols).find((k) =>
        (localCols[k] || []).some((t) => t.id === pageId),
      ) ||
      "";
    if (!from || from === status) return;

    setErr(null);
    moveLocal(pageId, from, status);
    start(async () => {
      const r = await updateNotionTaskStatusAction(lane, pageId, status, path);
      if (!r.ok) {
        setErr(r.error || "更新に失敗しました");
        setLocalCols(columns);
        return;
      }
      router.refresh();
    });
  }

  function onDragStart(e: React.DragEvent, task: NotionTask, from: string) {
    if (pending) {
      e.preventDefault();
      return;
    }
    const payload: DragPayload = { id: task.id, from };
    e.dataTransfer.setData("application/x-jarvis-task", JSON.stringify(payload));
    e.dataTransfer.setData("text/plain", task.id);
    e.dataTransfer.effectAllowed = "move";
    setDraggingId(task.id);
    setErr(null);
  }

  function onDragEnd() {
    setDraggingId(null);
    setDragOver(null);
  }

  function onDragOverCol(e: React.DragEvent, status: string) {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (dragOver !== status) setDragOver(status);
  }

  function onDropCol(e: React.DragEvent, to: string) {
    e.preventDefault();
    setDragOver(null);
    setDraggingId(null);
    let payload: DragPayload | null = null;
    try {
      const raw = e.dataTransfer.getData("application/x-jarvis-task");
      if (raw) payload = JSON.parse(raw) as DragPayload;
    } catch {
      payload = null;
    }
    if (!payload?.id || !payload.from) return;
    if (!statusChoices.includes(to)) return;
    onStatusChange(payload.id, to, payload.from);
  }

  if (!order.length) return null;

  return (
    <div className="notion-board-frame">
      {err ? <p className="err">{err}</p> : null}
      <p className="notion-board-dnd-hint meta">
        カードを別の列へドラッグ＆ドロップで移動できます（セレクトでも可）
        {pending ? " · 更新中…" : ""}
      </p>
      <div className="notion-board" role="region" aria-label="Kanban">
        {order.map((status) => {
          const tasks = localCols[status] || [];
          const isDropTarget = dragOver === status;
          return (
            <div
              className={
                isDropTarget ? "notion-col notion-col--drop" : "notion-col"
              }
              key={status}
              onDragOver={(e) => onDragOverCol(e, status)}
              onDragLeave={() => {
                if (dragOver === status) setDragOver(null);
              }}
              onDrop={(e) => onDropCol(e, status)}
            >
              <div className="notion-col-head">
                {status}{" "}
                <span className="notion-col-count">{tasks.length}</span>
              </div>
              <ul className="notion-col-list">
                {tasks.length === 0 ? (
                  <li className="notion-col-empty">ドロップ可</li>
                ) : (
                  tasks.map((t) => (
                    <li
                      key={t.id}
                      className={[
                        t.overdue ? "overdue" : "",
                        draggingId === t.id ? "notion-card--dragging" : "",
                        "notion-card",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                      draggable={!pending}
                      onDragStart={(e) => onDragStart(e, t, status)}
                      onDragEnd={onDragEnd}
                    >
                      <a
                        href={t.url}
                        target="_blank"
                        rel="noreferrer"
                        draggable={false}
                        onClick={(e) => {
                          if (draggingId === t.id) e.preventDefault();
                        }}
                      >
                        {t.title}
                      </a>
                      {t.due ? (
                        <span className="notion-col-due">
                          {t.overdue ? "期限切れ " : ""}
                          {t.due}
                        </span>
                      ) : null}
                      {statusChoices.length > 1 ? (
                        <label className="notion-status-move">
                          <span className="meta">移動</span>
                          <select
                            value={t.status}
                            disabled={pending}
                            onChange={(e) =>
                              onStatusChange(t.id, e.target.value, status)
                            }
                          >
                            {statusChoices.map((s) => (
                              <option key={s} value={s}>
                                {s}
                              </option>
                            ))}
                          </select>
                        </label>
                      ) : null}
                    </li>
                  ))
                )}
              </ul>
            </div>
          );
        })}
      </div>
    </div>
  );
}
