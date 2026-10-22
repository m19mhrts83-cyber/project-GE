/**
 * 313 Todoist完了候補確認 — Slack ボタン／署名 URL
 * 署名は PROPERTY_GATE_ACTION_TOKEN（116／511 と同系）
 */
import { createHmac, timingSafeEqual } from "crypto";
import { NextResponse } from "next/server";
import {
  closeTodoistTaskById,
  rescheduleTodoistTaskById,
} from "@/lib/todoistTasks";

export type Todoist313Action = "close" | "reschedule";

export const T313_ACTION_IDS = {
  close: "todoist_313_close",
  reschedule: "todoist_313_reschedule",
} as const;

function actionSecret(): string {
  // 本線 PROPERTY_GATE（116/511と同系）。無いときは TODOIST_API_TOKEN で署名
  return (
    (process.env.TODOIST_313_ACTION_TOKEN || "").trim() ||
    (process.env.PROPERTY_GATE_ACTION_TOKEN || "").trim() ||
    (process.env.MAIL_ACTION_TOKEN || "").trim() ||
    (process.env.TODOIST_API_TOKEN || "").trim()
  );
}

export function isTodoistTaskId(id: string): boolean {
  const s = (id || "").trim();
  // Todoist id は英数字（新APIは長い英数）
  return /^[a-zA-Z0-9_-]{6,64}$/.test(s);
}

export function parseT313Action(
  raw: string | null | undefined,
): Todoist313Action | null {
  const a = (raw || "").trim().toLowerCase();
  if (a === "close" || a === "done" || a === "complete") return "close";
  if (a === "reschedule" || a === "due" || a === "defer") return "reschedule";
  return null;
}

/** value: t313:close:{task_id} | t313:reschedule:{task_id}:{YYYY-MM-DD} */
export function parseT313ButtonValue(value: string): {
  action: Todoist313Action;
  taskId: string;
  due?: string;
} | null {
  const s = String(value || "").trim();
  const close = s.match(/^t313:close:([a-zA-Z0-9_-]{6,64})$/i);
  if (close && isTodoistTaskId(close[1])) {
    return { action: "close", taskId: close[1] };
  }
  const rs = s.match(
    /^t313:reschedule:([a-zA-Z0-9_-]{6,64}):(\d{4}-\d{2}-\d{2})$/i,
  );
  if (rs && isTodoistTaskId(rs[1])) {
    return { action: "reschedule", taskId: rs[1], due: rs[2] };
  }
  return null;
}

export function t313Sig(
  taskId: string,
  action: Todoist313Action,
  due?: string,
): string {
  const secret = actionSecret();
  const payload =
    action === "reschedule"
      ? `t313:${taskId}:${action}:${due || ""}`
      : `t313:${taskId}:${action}`;
  return createHmac("sha256", secret)
    .update(payload, "utf8")
    .digest("hex")
    .slice(0, 10);
}

export function t313SigOk(
  taskId: string,
  action: Todoist313Action,
  sig: string | null | undefined,
  due?: string,
): boolean {
  const expected = t313Sig(taskId, action, due);
  const got = (sig || "").trim().toLowerCase();
  if (!got || got.length !== expected.length) return false;
  try {
    return timingSafeEqual(Buffer.from(got), Buffer.from(expected));
  } catch {
    return false;
  }
}

export function t313ActionUrl(
  taskId: string,
  action: Todoist313Action,
  due?: string,
): string {
  const base = (
    process.env.JARVIS_DASHBOARD_URL ||
    process.env.NEXT_PUBLIC_SITE_URL ||
    "https://jarvis-dashboard-amber.vercel.app"
  )
    .trim()
    .replace(/\/$/, "");
  const s = t313Sig(taskId, action, due);
  if (action === "reschedule") {
    return `${base}/api/g/t313/reschedule/${encodeURIComponent(taskId)}?due=${encodeURIComponent(due || "")}&s=${s}`;
  }
  return `${base}/api/g/t313/close/${encodeURIComponent(taskId)}?s=${s}`;
}

export function htmlPage(title: string, body: string, ok: boolean) {
  const color = ok ? "#065f46" : "#991b1b";
  const esc = (x: string) =>
    String(x || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  return new NextResponse(
    `<!doctype html><html lang="ja"><meta charset="utf-8"/>
<title>${esc(title)}</title>
<body style="font-family:system-ui;padding:2rem;max-width:40rem;color:${color}">
<h1 style="font-size:1.25rem">${esc(title)}</h1>
<pre style="white-space:pre-wrap;background:#f3f4f6;padding:1rem;border-radius:8px;color:#111">${esc(body)}</pre>
<p style="color:#6b7280;font-size:0.875rem">このタブは閉じて大丈夫です。Slack に戻ってください。</p>
</body></html>`,
    {
      status: ok ? 200 : 400,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "private, no-store",
      },
    },
  );
}

export async function applyT313Action(opts: {
  action: Todoist313Action;
  taskId: string;
  due?: string;
  source: "slack_button" | "slack_link";
  n?: number;
}): Promise<{ ok: boolean; message: string }> {
  const id = opts.taskId.trim();
  if (!isTodoistTaskId(id)) {
    return { ok: false, message: "task_id が不正です" };
  }
  const author =
    (process.env.TODOIST_313_AUTHOR || "").trim() || "FRIDAY";
  const markN = opts.n != null ? String(opts.n) : "";

  if (opts.action === "close") {
    const comment =
      `【${author}】タスク完了したよ（松野確認OK）\n` +
      `サマリ: 313 Slack${opts.source === "slack_button" ? "ボタン" : "リンク"} — 完了` +
      (markN ? ` ✅${markN}` : "") +
      `\nアウトプット:\n- [該当タスク](https://app.todoist.com/app/task/${id})\n`;
    const r = await closeTodoistTaskById(id, comment);
    if (!r.ok) return { ok: false, message: r.error };
    return {
      ok: true,
      message:
        `完了しました` +
        (markN ? `（✅${markN}）` : "") +
        `\nhttps://app.todoist.com/app/task/${id}`,
    };
  }

  const due = (opts.due || "").trim().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(due)) {
    return { ok: false, message: "延期日（due）が不正です" };
  }
  const comment =
    `【${author}】\n` +
    `サマリ: 期日を ${due} へリスケ（313 Slack` +
    `${opts.source === "slack_button" ? "ボタン" : "リンク"}` +
    (markN ? `・📅${markN}` : "") +
    `）\n` +
    `アウトプット:\n- [該当タスク](https://app.todoist.com/app/task/${id})\n`;
  const r = await rescheduleTodoistTaskById(id, due, comment);
  if (!r.ok) return { ok: false, message: r.error };
  return {
    ok: true,
    message:
      `期日を ${due} へ延期しました` +
      (markN ? `（📅${markN}）` : "") +
      `\nhttps://app.todoist.com/app/task/${id}`,
  };
}
