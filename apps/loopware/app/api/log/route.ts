import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { writeDecision } from "@/lib/ownerDecisionLog";
import { SURFACES, tally, weekStartIso, type DecisionInput } from "@/lib/decisionContract";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_BATCH = 50;

/**
 * 判断を1件または複数件（端末で溜めた分の再送）記録する。
 * body: { decision: DecisionInput } または { decisions: DecisionInput[] }
 * 入口を書かなければ loopware とみなす。
 */
export async function POST(req: Request) {
  let body: { decision?: DecisionInput; decisions?: DecisionInput[] };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }
  const list = (body.decisions || (body.decision ? [body.decision] : [])).slice(0, MAX_BATCH + 1);
  if (!list.length) return NextResponse.json({ ok: false, error: "no decision" }, { status: 400 });
  if (list.length > MAX_BATCH) {
    return NextResponse.json({ ok: false, error: `too many (max ${MAX_BATCH})` }, { status: 413 });
  }
  const sb = serviceClient();
  const results = [];
  for (const d of list) {
    results.push(await writeDecision(sb, { ...d, source: d.source || "loopware" }));
  }
  const bad = results.filter((r) => !r.ok).length;
  return NextResponse.json({ ok: bad === 0, results }, { status: bad === list.length ? 400 : 200 });
}

/** 今週のログの粒。?surface=triage（前方一致: triage, triage_miss, triage_rule） */
export async function GET(req: Request) {
  const surface = new URL(req.url).searchParams.get("surface") || "";
  if (surface && !SURFACES.some((s) => s.startsWith(surface))) {
    return NextResponse.json({ ok: false, error: "unknown surface" }, { status: 400 });
  }
  const sb = serviceClient();
  const since = weekStartIso();
  if (!sb) return NextResponse.json({ ok: true, persisted: false, since, tally: tally([]) });
  let q = sb.from("owner_decisions").select("action,payload").gte("decided_at", since).limit(2000);
  if (surface) q = q.like("surface", `${surface}%`);
  const { data, error } = await q;
  if (error) return NextResponse.json({ ok: true, persisted: false, since, tally: tally([]), reason: error.message });
  return NextResponse.json({ ok: true, persisted: true, since, tally: tally(data || []) });
}
