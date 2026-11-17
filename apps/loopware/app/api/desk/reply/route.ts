import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { writeDecision } from "@/lib/ownerDecisionLog";
import { draftViaDashboard, loadPastReplies, sendViaDashboard, type DraftOp } from "@/lib/desk";
import { isDeskItemId } from "@/lib/deskCore";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// 下書き作成は Mac の定額 AI を待つ（Jarvis 側で最大 55 秒）
export const maxDuration = 90;

/**
 * 判断デスクの返信欄（2026-11-17）。
 * GET  ?item=<id>  → この相手に過去に送った返信と、やり取り md の末尾（AI は使わない）
 * POST { itemId, op: compose|proofread|revise|send, draft?, instruction?, to?, account?, openedAt?, assist? }
 */
export async function GET(req: Request) {
  const id = new URL(req.url).searchParams.get("item") || "";
  if (!isDeskItemId(id)) return NextResponse.json({ ok: false, error: "item が不正です" }, { status: 400 });
  const sb = serviceClient();
  const [past, ctx] = await Promise.all([
    sb ? loadPastReplies(sb, id).catch(() => []) : Promise.resolve([]),
    draftViaDashboard(id, "context", {}).catch(() => null),
  ]);
  return NextResponse.json(
    { ok: true, past, log: ctx?.ok ? ctx.log || null : null, logNotice: ctx?.message || ctx?.log?.notice || "" },
    { headers: { "cache-control": "private, no-store" } },
  );
}

type Body = {
  itemId?: string;
  op?: string;
  draft?: string;
  instruction?: string;
  to?: string;
  account?: string;
  openedAt?: number;
  assist?: { proofread?: number; revise?: number };
  subject?: string;
  input?: "voice" | "text";
  /** 指示1回ごとの鍵（作成中の再試行でもコメントは1行だけ） */
  idemKey?: string;
};

export async function POST(req: Request) {
  let b: Body;
  try {
    b = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ ok: false, message: "bad json" }, { status: 400 });
  }
  const id = String(b.itemId || "");
  if (!isDeskItemId(id)) return NextResponse.json({ ok: false, message: "itemId が不正です" }, { status: 400 });
  const op = String(b.op || "");

  if (op === "send") {
    const body = String(b.draft || "").trim();
    if (!body) return NextResponse.json({ ok: false, message: "本文が空です" }, { status: 400 });
    const r = await sendViaDashboard(id, {
      body,
      to: String(b.to || "").trim() || undefined,
      account: String(b.account || "").trim() || undefined,
      openedAt: Number(b.openedAt) || undefined,
      assist: b.assist,
    });
    // 判断ログの行（action=sent）は Jarvis 側の状態変更でトリガーが残す
    return NextResponse.json(r, { status: r.ok ? 200 : 409 });
  }

  if (op !== "compose" && op !== "proofread" && op !== "revise") {
    return NextResponse.json({ ok: false, message: "op が不正です" }, { status: 400 });
  }
  const instruction = String(b.instruction || "").trim().slice(0, 2000);

  // 声・文字での指示は、そのまま判断ログのコメントとして残す（理由は補わない）
  if (instruction && op !== "proofread") {
    await writeDecision(serviceClient(), {
      surface: "triage",
      action: "comment",
      source: "loopware",
      targetType: "triage_item",
      targetId: id,
      subject: String(b.subject || "").slice(0, 200),
      note: instruction,
      idemKey: String(b.idemKey || "").slice(0, 120) || `lw-reply-${op}-${id}-${Date.now().toString(36)}`,
      payload: { input: b.input === "voice" ? "voice" : "text", step: op === "compose" ? "reply_compose" : "reply_revise" },
    }).catch(() => undefined);
  }

  const r = await draftViaDashboard(id, op as DraftOp, { draft: String(b.draft || ""), instruction });
  return NextResponse.json(r, { status: r.ok || r.pending ? 200 : 409 });
}
