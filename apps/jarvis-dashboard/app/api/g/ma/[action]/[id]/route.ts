import { NextResponse, type NextRequest } from "next/server";
import {
  applyMailActionSlack,
  editFormHtml,
  fetchMailActionTriage,
  htmlPage,
  isMailActionTriageId,
  maSigOk,
  parseMaAction,
} from "@/lib/mailActionSlackAction";

export const runtime = "nodejs";

/**
 * メール要対応 Slack 操作（ログイン不要・HMAC）
 *   返信フォーム: GET /api/g/ma/reply/{triage_id}?s=
 *   見送り:       GET /api/g/ma/skip/{triage_id}?s=
 *   Todoist:      GET /api/g/ma/todoist/{triage_id}?s=
 *   返信送信:     POST /api/g/ma/reply/{id}（body + intent=send）
 */

export async function GET(
  request: NextRequest,
  ctx: { params: Promise<{ action: string; id: string }> },
) {
  const { action: actionRaw, id: idRaw } = await ctx.params;
  const id = decodeURIComponent(idRaw || "").trim();
  const action = parseMaAction(actionRaw);
  if (!id || !isMailActionTriageId(id) || !action) {
    return htmlPage("エラー", "action または triage_id が不正です", false);
  }

  const sig = request.nextUrl.searchParams.get("s");
  if (!maSigOk(id, action, sig)) {
    return htmlPage(
      "認証エラー",
      "署名が無効です（リンクが古い／トークン不一致の可能性）",
      false,
    );
  }

  if (request.nextUrl.searchParams.get("cancel") === "1") {
    return htmlPage("キャンセル", "編集をキャンセルしました", true);
  }

  if (action === "reply") {
    const row = await fetchMailActionTriage(id);
    if (!row) {
      return htmlPage("エラー", "対象のメール要対応が見つかりません", false);
    }
    if (String(row.status) === "sent") {
      return htmlPage("送信済み", "すでに送信済みです", true);
    }
    return new NextResponse(editFormHtml(row, String(sig || "")), {
      status: 200,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "private, no-store",
      },
    });
  }

  const result = await applyMailActionSlack(id, action, {
    source: "slack_short_link",
  });
  const title =
    action === "skip"
      ? "見送り"
      : action === "todoist"
        ? "Todoist"
        : "完了";
  const msg =
    action === "skip" && result.ok
      ? `${result.message}\n\nSlack 上のカードは削除しました（または削除済み）。`
      : result.message;
  return htmlPage(result.ok ? title : "失敗", msg, result.ok);
}

export async function POST(
  request: NextRequest,
  ctx: { params: Promise<{ action: string; id: string }> },
) {
  const { action: actionRaw, id: idRaw } = await ctx.params;
  const id = decodeURIComponent(idRaw || "").trim();
  const action = parseMaAction(actionRaw);
  if (!id || !isMailActionTriageId(id) || action !== "reply") {
    return htmlPage("エラー", "返信送信のみ POST できます", false);
  }

  const form = await request.formData();
  const sig = String(form.get("s") || "");
  if (!maSigOk(id, "reply", sig)) {
    return htmlPage("認証エラー", "署名が無効です", false);
  }
  const body = String(form.get("body") || "");
  const intent = String(form.get("intent") || "send");
  if (intent !== "send") {
    return htmlPage("キャンセル", "送信しませんでした", true);
  }

  const result = await applyMailActionSlack(id, "reply", {
    body,
    source: "slack_edit_form",
  });
  return htmlPage(
    result.ok ? "送信完了" : "失敗",
    result.message,
    result.ok,
  );
}

export async function HEAD() {
  return new NextResponse(null, { status: 200 });
}
