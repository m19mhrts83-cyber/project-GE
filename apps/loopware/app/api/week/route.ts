import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { writeDecision } from "@/lib/ownerDecisionLog";
import type { DecisionInput } from "@/lib/decisionContract";
import type { Calendar, Snapshot } from "@/lib/weekPick";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_ROWS = 120;

function parse<T>(v: unknown): T | null {
  try {
    return JSON.parse(String(v || "")) as T;
  } catch {
    return null;
  }
}

/**
 * 今週の9件の材料（sync_meta.weekly_pick_snapshot・weekly_pick_calendar）と、
 * その週の確定の状態（確定済みか・Todoist へ反映済みか）。
 */
export async function GET() {
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  const { data: metas, error } = await sb
    .from("sync_meta")
    .select("key,value,updated_at")
    .in("key", ["weekly_pick_snapshot", "weekly_pick_calendar"]);
  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  const snapshot = parse<Snapshot>(metas?.find((m) => m.key === "weekly_pick_snapshot")?.value);
  const calendar = parse<Calendar>(metas?.find((m) => m.key === "weekly_pick_calendar")?.value);

  let commit: { id: number; decided_at: string } | null = null;
  let applied: { decided_at: string; result: unknown } | null = null;
  if (snapshot?.week) {
    const { data: c } = await sb
      .from("owner_decisions")
      .select("id,decided_at")
      .eq("surface", "weekly_pick")
      .eq("action", "commit")
      .eq("target_id", snapshot.week)
      .order("decided_at", { ascending: false })
      .limit(1)
      .maybeSingle();
    if (c) {
      commit = { id: Number(c.id), decided_at: String(c.decided_at) };
      const { data: a } = await sb
        .from("owner_decisions")
        .select("decided_at,payload")
        .eq("surface", "weekly_pick")
        .eq("action", "done")
        .eq("target_id", String(c.id))
        .limit(1)
        .maybeSingle();
      if (a) applied = { decided_at: String(a.decided_at), result: (a.payload as { result?: unknown } | null)?.result ?? null };
    }
  }
  return NextResponse.json({ ok: true, snapshot, calendar, commit, applied });
}

/** 確定。判断の行を全部書いてから、最後に commit（反映の単位）を書く */
export async function POST(req: Request) {
  let body: { decisions?: DecisionInput[] };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }
  const list = (body.decisions || []).filter((d) => d && d.surface === "weekly_pick");
  if (!list.length) return NextResponse.json({ ok: false, error: "no decisions" }, { status: 400 });
  if (list.length > MAX_ROWS) return NextResponse.json({ ok: false, error: `too many (max ${MAX_ROWS})` }, { status: 413 });
  const commits = list.filter((d) => d.action === "commit");
  if (commits.length !== 1) return NextResponse.json({ ok: false, error: "commit が1つ必要" }, { status: 400 });
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });

  let saved = 0;
  const failed: string[] = [];
  for (const d of list.filter((x) => x.action !== "commit")) {
    const r = await writeDecision(sb, { ...d, source: "loopware" });
    if (r.ok && r.persisted) saved += 1;
    else failed.push(`${d.action}:${d.targetId}`);
  }
  const c = await writeDecision(sb, { ...commits[0], source: "loopware" });
  const committed = c.ok && c.persisted;
  return NextResponse.json(
    { ok: committed, saved, failed, committed, reason: !committed ? (c.ok ? (c as { reason?: string }).reason : c.error) : undefined },
    { status: committed ? 200 : 500 },
  );
}
