import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { writeDecision } from "@/lib/ownerDecisionLog";
import { applyVerdict, pendingFixes } from "@/lib/zaimCore";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const WATCH_ID = "zaim_quality";

/** Zaim の週次見直し: 学習した費目の直しを 正しい／違う で確かめる（surface=zaim_category） */
export async function GET() {
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  const { data, error } = await sb.from("watch_status").select("payload,updated_at").eq("id", WATCH_ID).maybeSingle();
  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  const pl = (data?.payload || {}) as Record<string, unknown>;
  return NextResponse.json({
    ok: true,
    updatedAt: data?.updated_at || null,
    fixes: pendingFixes(pl),
    categoryReviewCount: Number(pl.category_review_count || 0),
  });
}

export async function POST(req: Request) {
  let b: { id?: string; verdict?: "good" | "wrong"; note?: string; idemKey?: string };
  try {
    b = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }
  const id = String(b.id || "").trim();
  const key = String(b.idemKey || "");
  if (!id || id.length > 200 || (b.verdict !== "good" && b.verdict !== "wrong") || key.length < 8) {
    return NextResponse.json({ ok: false, error: "id / verdict / idemKey" }, { status: 400 });
  }
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  const { data, error } = await sb.from("watch_status").select("payload").eq("id", WATCH_ID).maybeSingle();
  if (error || !data) return NextResponse.json({ ok: false, error: error?.message || "Zaim Watch が未 push です" }, { status: 500 });
  const now = new Date().toISOString();
  const next = b.verdict === "good" ? "confirmed" : "disputed";
  const { payload, found } = applyVerdict((data.payload || {}) as Record<string, unknown>, id, next, now);
  if (!found) return NextResponse.json({ ok: false, error: "その直しは見つかりません" }, { status: 404 });
  const { error: uErr } = await sb.from("watch_status").update({ payload, updated_at: now }).eq("id", WATCH_ID);
  if (uErr) return NextResponse.json({ ok: false, error: uErr.message }, { status: 500 });
  const note = String(b.note || "").trim().slice(0, 800);
  if (next === "disputed") {
    // Mac の学習係はコメントと disputed を見て、その店の学習を止める（ダッシュボードと同じ）
    await sb.from("watch_comments").insert({ watch_id: WATCH_ID, role: "user", body: note ? `学習が違う: ${id}\n${note}` : `学習が違う: ${id}` });
  }
  const fix = ((payload.recent_fixes as Record<string, unknown>[]) || []).find((f) => String(f.id || "") === id) || {};
  const r = await writeDecision(sb, {
    surface: "zaim_category",
    action: b.verdict,
    source: "loopware",
    employee: "613",
    targetType: "zaim_fix",
    targetId: id,
    subject: String(fix.proposal || "").slice(0, 200) || null,
    note: note || null,
    idemKey: key,
  });
  return NextResponse.json(r, { status: r.ok ? 200 : 400 });
}
