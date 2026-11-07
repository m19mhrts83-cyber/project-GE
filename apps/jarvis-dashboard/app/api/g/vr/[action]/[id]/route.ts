import { NextResponse, type NextRequest } from "next/server";
import {
  applyVendorReplySlack,
  confirmActionHtml,
  editFormHtml,
  fetchVendorReplyTriage,
  htmlPage,
  isVendorReplyTriageId,
  parseVrAction,
  vrSigOk,
} from "@/lib/vendorReplySlackAction";

export const runtime = "nodejs";

/**
 * 業者返信 Slack 操作（ログイン不要・HMAC）
 *   送信:     GET は確認画面のみ → POST で確定
 *   返信なし: GET は確認画面のみ → POST で確定
 *   編集:     GET /api/g/vr/edit/{triage_id}?s= → HTML フォーム
 *             POST 同URL（body + intent=send）
 */

export async function GET(
  request: NextRequest,
  ctx: { params: Promise<{ action: string; id: string }> },
) {
  const { action: actionRaw, id: idRaw } = await ctx.params;
  const id = decodeURIComponent(idRaw || "").trim();
  const action = parseVrAction(actionRaw);
  if (!id || !isVendorReplyTriageId(id) || !action) {
    return htmlPage("エラー", "action または triage_id が不正です", false);
  }

  const sig = request.nextUrl.searchParams.get("s");
  if (!vrSigOk(id, action, sig)) {
    return htmlPage(
      "認証エラー",
      "署名が無効です（リンクが古い／トークン不一致の可能性）",
      false,
    );
  }

  if (request.nextUrl.searchParams.get("cancel") === "1") {
    return htmlPage("キャンセル", "編集をキャンセルしました", true);
  }

  if (action === "edit") {
    const row = await fetchVendorReplyTriage(id);
    if (!row) {
      return htmlPage("エラー", "対象の業者返信が見つかりません", false);
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

  const row = await fetchVendorReplyTriage(id);
  if (!row) {
    return htmlPage("エラー", "対象の業者返信が見つかりません", false);
  }
  if (String(row.status) === "sent") {
    return htmlPage("送信済み", "すでに送信済みです", true);
  }
  return new NextResponse(confirmActionHtml(row, action, String(sig || "")), {
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
  const { action: actionRaw, id: idRaw } = await ctx.params;
  const id = decodeURIComponent(idRaw || "").trim();
  const action = parseVrAction(actionRaw);
  if (!id || !isVendorReplyTriageId(id) || !action) {
    return htmlPage("エラー", "action または triage_id が不正です", false);
  }

  const form = await request.formData();
  const sig = String(form.get("s") || "");
  if (!vrSigOk(id, action, sig)) {
    return htmlPage("認証エラー", "署名が無効です", false);
  }
  const body = action === "edit" ? String(form.get("body") || "") : undefined;
  const intent = String(form.get("intent") || "");
  if ((action === "edit" && intent !== "send") || (action !== "edit" && intent !== "confirm")) {
    return htmlPage("キャンセル", "送信しませんでした", true);
  }

  const applyAction = action === "edit" ? "send" : action;
  const result = await applyVendorReplySlack(id, applyAction, {
    body,
    source: action === "edit" ? "slack_edit_form" : "slack_confirmation_form",
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
