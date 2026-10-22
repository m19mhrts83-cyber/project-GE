import { NextResponse, type NextRequest } from "next/server";
import {
  applyT313Action,
  htmlPage,
  isTodoistTaskId,
  parseT313Action,
  t313SigOk,
} from "@/lib/todoist313SlackAction";
import { t313ConfirmHtml } from "@/lib/todoist313SlackInteract";

export const runtime = "nodejs";

/**
 * 313 Slack 操作（ログイン不要・HMAC）
 *   完了:   GET/POST /api/g/t313/close/{task_id}?s=
 *   延期:   GET/POST /api/g/t313/reschedule/{task_id}?due=YYYY-MM-DD&s=
 * GET は確認画面のみ（リンク展開で即実行しない）。POST + intent=confirm で実行。
 */

export async function GET(
  request: NextRequest,
  ctx: { params: Promise<{ action: string; id: string }> },
) {
  const { action: rawAction, id } = await ctx.params;
  const action = parseT313Action(rawAction);
  const taskId = decodeURIComponent(id || "").trim();
  const sp = request.nextUrl.searchParams;
  const sig = sp.get("s");
  const due = (sp.get("due") || "").trim().slice(0, 10);

  if (!action || !isTodoistTaskId(taskId)) {
    return htmlPage("エラー", "action と task_id が必要です", false);
  }
  if (!t313SigOk(taskId, action, sig, action === "reschedule" ? due : undefined)) {
    return htmlPage(
      "認証エラー",
      "署名が無効です。PROPERTY_GATE_ACTION_TOKEN を確認してください。",
      false,
    );
  }
  if (action === "reschedule" && !/^\d{4}-\d{2}-\d{2}$/.test(due)) {
    return htmlPage("エラー", "due=YYYY-MM-DD が必要です", false);
  }
  if (sp.get("cancel") === "1") {
    return htmlPage("キャンセル", "実行しませんでした。", true);
  }

  const html = t313ConfirmHtml({
    action,
    taskId,
    due: action === "reschedule" ? due : undefined,
    sig: (sig || "").trim(),
  });
  return new NextResponse(html, {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "private, no-store",
    },
  });
}

export async function POST(
  request: NextRequest,
  ctx: { params: Promise<{ action: string; id: string }> },
) {
  const { action: rawAction, id } = await ctx.params;
  const action = parseT313Action(rawAction);
  const taskId = decodeURIComponent(id || "").trim();
  const ct = request.headers.get("content-type") || "";
  let sig = "";
  let due = "";
  let intent = "";

  if (ct.includes("application/x-www-form-urlencoded") || ct.includes("multipart/form-data")) {
    const form = await request.formData();
    sig = String(form.get("s") || "").trim();
    due = String(form.get("due") || "").trim().slice(0, 10);
    intent = String(form.get("intent") || "").trim();
  } else {
    const sp = request.nextUrl.searchParams;
    sig = (sp.get("s") || "").trim();
    due = (sp.get("due") || "").trim().slice(0, 10);
    intent = (sp.get("intent") || "confirm").trim();
  }

  if (!action || !isTodoistTaskId(taskId)) {
    return htmlPage("エラー", "action と task_id が必要です", false);
  }
  if (intent !== "confirm") {
    return htmlPage("キャンセル", "実行しませんでした。", true);
  }
  if (!t313SigOk(taskId, action, sig, action === "reschedule" ? due : undefined)) {
    return htmlPage("認証エラー", "署名が無効です。", false);
  }
  if (action === "reschedule" && !/^\d{4}-\d{2}-\d{2}$/.test(due)) {
    return htmlPage("エラー", "due=YYYY-MM-DD が必要です", false);
  }

  const result = await applyT313Action({
    action,
    taskId,
    due: action === "reschedule" ? due : undefined,
    source: "slack_link",
  });
  const title =
    action === "close"
      ? result.ok
        ? "完了"
        : "完了失敗"
      : result.ok
        ? "延期"
        : "延期失敗";
  return htmlPage(title, result.message, result.ok);
}
