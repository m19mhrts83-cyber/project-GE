import { NextResponse, type NextRequest } from "next/server";
import {
  applyT312Action,
  decodeT312Proposal,
  htmlPage,
  parseT312Action,
  t312SigOk,
} from "@/lib/todoist312SlackAction";
import { t312ConfirmHtml } from "@/lib/todoist312SlackInteract";

export const runtime = "nodejs";

/**
 * 312 Slack 操作（ログイン不要・HMAC）
 *   起票:   GET/POST /api/g/t312/create/{n}?p=&s=
 *   見送り: GET/POST /api/g/t312/dismiss/{n}?p=&s=
 * GET は確認画面のみ。POST + intent=confirm で実行。
 */

export async function GET(
  request: NextRequest,
  ctx: { params: Promise<{ action: string; id: string }> },
) {
  const { action: rawAction } = await ctx.params;
  const action = parseT312Action(rawAction);
  const sp = request.nextUrl.searchParams;
  const sig = sp.get("s");
  const payloadB64 = (sp.get("p") || "").trim();

  if (!action || !payloadB64) {
    return htmlPage("エラー", "action と p（提案ペイロード）が必要です", false);
  }
  if (!t312SigOk(action, payloadB64, sig)) {
    return htmlPage(
      "認証エラー",
      "署名が無効です。投稿側と Vercel の署名キー（PROPERTY_GATE_ACTION_TOKEN または TODOIST_API_TOKEN）を揃えてください。",
      false,
    );
  }
  const proposal = decodeT312Proposal(payloadB64);
  if (!proposal) {
    return htmlPage("エラー", "提案ペイロードが不正です", false);
  }
  if (sp.get("cancel") === "1") {
    return htmlPage("キャンセル", "実行しませんでした。", true);
  }

  const html = t312ConfirmHtml({
    action,
    proposal,
    payloadB64,
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
  const { action: rawAction } = await ctx.params;
  const action = parseT312Action(rawAction);
  const ct = request.headers.get("content-type") || "";
  let sig = "";
  let payloadB64 = "";
  let intent = "";

  if (
    ct.includes("application/x-www-form-urlencoded") ||
    ct.includes("multipart/form-data")
  ) {
    const form = await request.formData();
    sig = String(form.get("s") || "").trim();
    payloadB64 = String(form.get("p") || "").trim();
    intent = String(form.get("intent") || "").trim();
  } else {
    const sp = request.nextUrl.searchParams;
    sig = (sp.get("s") || "").trim();
    payloadB64 = (sp.get("p") || "").trim();
    intent = (sp.get("intent") || "confirm").trim();
  }

  if (!action || !payloadB64) {
    return htmlPage("エラー", "action と p が必要です", false);
  }
  if (intent !== "confirm") {
    return htmlPage("キャンセル", "実行しませんでした。", true);
  }
  if (!t312SigOk(action, payloadB64, sig)) {
    return htmlPage("認証エラー", "署名が無効です。", false);
  }
  const proposal = decodeT312Proposal(payloadB64);
  if (!proposal) {
    return htmlPage("エラー", "提案ペイロードが不正です", false);
  }

  const result = await applyT312Action({
    action,
    proposal,
    source: "slack_link",
  });
  const title =
    action === "create"
      ? result.ok
        ? "起票"
        : "起票失敗"
      : result.ok
        ? "見送り"
        : "見送り失敗";
  return htmlPage(title, result.message, result.ok);
}
