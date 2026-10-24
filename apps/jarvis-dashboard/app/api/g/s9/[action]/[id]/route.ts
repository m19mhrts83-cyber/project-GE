import { NextResponse, type NextRequest } from "next/server";
import {
  applyS9Action,
  confirmHtml,
  decodeS9Candidate,
  htmlPage,
  parseS9Action,
  s9SigOk,
} from "@/lib/s9SlackAction";

export const runtime = "nodejs";

/**
 * S9 管理会社 採用／見送り（ログイン不要・HMAC）
 *   採用:   GET/POST /api/g/s9/adopt/n1?p=&s=
 *   見送り: GET/POST /api/g/s9/skip/n1?p=&s=
 * GET は確認画面のみ。POST + intent=confirm で実行。
 */
export async function GET(
  request: NextRequest,
  ctx: { params: Promise<{ action: string; id: string }> },
) {
  const { action: rawAction } = await ctx.params;
  const action = parseS9Action(rawAction);
  const sp = request.nextUrl.searchParams;
  const sig = sp.get("s");
  const payloadB64 = (sp.get("p") || "").trim();

  if (!action || !payloadB64) {
    return htmlPage("エラー", "action と p（候補データ）が必要です", false);
  }
  if (!s9SigOk(action, payloadB64, sig)) {
    return htmlPage(
      "認証エラー",
      "署名が無効です。投稿側と Vercel の署名キー（PROPERTY_GATE_ACTION_TOKEN 等）を揃えてください。",
      false,
    );
  }
  const candidate = decodeS9Candidate(payloadB64);
  if (!candidate) {
    return htmlPage("エラー", "候補データが不正です", false);
  }
  if (sp.get("cancel") === "1") {
    return htmlPage("キャンセル", "実行しませんでした。", true);
  }
  return confirmHtml({
    decision: action,
    candidate,
    payloadB64,
    sig: (sig || "").trim(),
  });
}

export async function POST(
  request: NextRequest,
  ctx: { params: Promise<{ action: string; id: string }> },
) {
  const { action: rawAction } = await ctx.params;
  const action = parseS9Action(rawAction);
  const ct = request.headers.get("content-type") || "";
  let sig = "";
  let payloadB64 = "";
  let intent = "";
  let channelId = "";
  let messageTs = "";

  if (
    ct.includes("application/x-www-form-urlencoded") ||
    ct.includes("multipart/form-data")
  ) {
    const form = await request.formData();
    sig = String(form.get("s") || "").trim();
    payloadB64 = String(form.get("p") || "").trim();
    intent = String(form.get("intent") || "").trim();
    channelId = String(form.get("channel") || "").trim();
    messageTs = String(form.get("ts") || "").trim();
  } else {
    const sp = request.nextUrl.searchParams;
    sig = (sp.get("s") || "").trim();
    payloadB64 = (sp.get("p") || "").trim();
    intent = (sp.get("intent") || "confirm").trim();
    channelId = (sp.get("channel") || "").trim();
    messageTs = (sp.get("ts") || "").trim();
  }

  if (!action || !payloadB64) {
    return htmlPage("エラー", "action と p が必要です", false);
  }
  if (intent !== "confirm") {
    return htmlPage("キャンセル", "実行しませんでした。", true);
  }
  if (!s9SigOk(action, payloadB64, sig)) {
    return htmlPage("認証エラー", "署名が無効です。", false);
  }
  const candidate = decodeS9Candidate(payloadB64);
  if (!candidate) {
    return htmlPage("エラー", "候補データが不正です", false);
  }

  const result = await applyS9Action({
    decision: action,
    candidate,
    source: "slack_link",
    channelId,
    messageTs,
  });
  const label = action === "adopt" ? "採用" : "見送り";
  return htmlPage(
    result.ok ? `${label}を受け付けました` : `${label}に失敗`,
    result.message +
      (result.jobId ? `\njob_id=${result.jobId.slice(0, 8)}…` : ""),
    result.ok,
  );
}
