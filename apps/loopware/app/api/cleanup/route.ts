import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { writeDecision } from "@/lib/ownerDecisionLog";
import type { DecisionInput } from "@/lib/decisionContract";
import type { CleanupSnapshot } from "@/lib/cleanupBulk";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_ROWS = 150;

/** 片付け候補（sync_meta.todoist_cleanup_snapshot）と、反映待ちの件数 */
export async function GET() {
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  const { data, error } = await sb.from("sync_meta").select("value,updated_at").eq("key", "todoist_cleanup_snapshot").maybeSingle();
  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  let snapshot: CleanupSnapshot | null = null;
  try {
    snapshot = data?.value ? (JSON.parse(String(data.value)) as CleanupSnapshot) : null;
  } catch {
    snapshot = null;
  }
  return NextResponse.json({ ok: true, snapshot });
}

/** 確定。選んだカードだけ判断の行を書く（反映は 30 分ごとのスクリプトが Todoist に行う） */
export async function POST(req: Request) {
  let body: { decisions?: DecisionInput[] };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }
  const list = (body.decisions || []).filter(
    (d) => d && d.surface === "todoist_313" && d.targetType === "todoist_task" && (d.payload as { bulk?: boolean } | undefined)?.bulk,
  );
  if (!list.length) return NextResponse.json({ ok: false, error: "no decisions" }, { status: 400 });
  if (list.length > MAX_ROWS) return NextResponse.json({ ok: false, error: `too many (max ${MAX_ROWS})` }, { status: 413 });
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  let saved = 0;
  const failed: string[] = [];
  for (const d of list) {
    const r = await writeDecision(sb, { ...d, source: "loopware" });
    if (r.ok && r.persisted) saved += 1;
    else failed.push(`${d.action}:${d.targetId}`);
  }
  return NextResponse.json({ ok: failed.length === 0, saved, failed }, { status: failed.length ? 207 : 200 });
}
