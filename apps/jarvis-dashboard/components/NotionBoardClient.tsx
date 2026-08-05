"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { updateNotionTaskStatusAction } from "@/app/actions/notionBoard";
import type { NotionTask } from "@/lib/notionTasks";

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
  const order =
    columnOrder.length > 0 ? columnOrder : Object.keys(columns);
  const statusChoices =
    moveStatuses.length > 0
      ? moveStatuses
      : openStatuses.length > 0
        ? openStatuses
        : order;

  function onStatusChange(pageId: string, status: string) {
    setErr(null);
    start(async () => {
      const r = await updateNotionTaskStatusAction(lane, pageId, status, path);
      if (!r.ok) {
        setErr(r.error || "更新に失敗しました");
        return;
      }
      router.refresh();
    });
  }

  if (!order.length) return null;

  return (
    <div className="notion-board-frame">
      {err ? <p className="err">{err}</p> : null}
      <div className="notion-board" role="region" aria-label="Kanban">
        {order.map((status) => {
          const tasks = columns[status] || [];
          return (
            <div className="notion-col" key={status}>
              <div className="notion-col-head">
                {status}{" "}
                <span className="notion-col-count">{tasks.length}</span>
              </div>
              <ul className="notion-col-list">
                {tasks.length === 0 ? (
                  <li className="notion-col-empty">—</li>
                ) : (
                  tasks.map((t) => (
                    <li key={t.id} className={t.overdue ? "overdue" : undefined}>
                      <a href={t.url} target="_blank" rel="noreferrer">
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
                              onStatusChange(t.id, e.target.value)
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
