import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";

export const runtime = "nodejs";

type Body = {
  op?: "add" | "delete" | "reassign";
  comment?: {
    id: string;
    agentId: string;
    targetId: string;
    targetLabel: string;
    text: string;
    at: string;
    via: "voice" | "text";
    startedAt?: string;
    mode?: string;
    alt?: { id: string; label: string };
    fromTargetId?: string;
  };
};

/**
 * 音声（・文字）コメントを判断ログ（owner_decisions）へ追記する。
 * 追記のみ：削除は「voice_comment_deleted」を足すだけで、元の行は残す。
 */
export async function POST(req: Request) {
  let body: Body;
  try {
    body = (await req.json()) as Body;
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }
  const c = body.comment;
  if (!c?.id || !c.targetId) {
    return NextResponse.json({ ok: false, error: "no comment" }, { status: 400 });
  }

  const sb = serviceClient();
  if (!sb) {
    return NextResponse.json({ ok: true, persisted: false, reason: "supabase_unconfigured" });
  }

  try {
    const { error } = await sb.from("owner_decisions").insert({
      surface: "loopware_voice",
      action:
        body.op === "delete"
          ? "voice_comment_deleted"
          : body.op === "reassign"
            ? "voice_comment_reassigned"
            : "voice_comment",
      source: "app",
      employee: c.agentId,
      target_type: "loopware_card",
      target_id: c.targetId,
      subject: (c.targetLabel || "").slice(0, 500),
      note: c.text.slice(0, 2000),
      payload: {
        kind: "loopware",
        via: c.via,
        comment_id: c.id,
        commented_at: c.at,
        agent_id: c.agentId,
        started_at: c.startedAt || null,
        mode: c.mode || null,
        alt_target_id: c.alt?.id || null,
        alt_target_label: c.alt?.label || null,
        from_target_id: c.fromTargetId || null,
      },
    });
    if (error) {
      return NextResponse.json({ ok: true, persisted: false, reason: error.message });
    }
    return NextResponse.json({ ok: true, persisted: true, via: "owner_decisions" });
  } catch (e) {
    return NextResponse.json({
      ok: true,
      persisted: false,
      reason: e instanceof Error ? e.message : String(e),
    });
  }
}
