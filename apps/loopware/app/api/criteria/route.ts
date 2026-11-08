import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";

export const runtime = "nodejs";

type Criterion = { id: string; text: string; range: string; basis: string; at: string };

/**
 * 基準（本人が承認したもの）。追記のみ：承認・編集・取り消し・レビュー完了を owner_decisions に足し、
 * 現在の一覧はその履歴を順に読んで作る。元の判断やAIの解釈とは別に持つ。
 */
export async function GET() {
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: true, configured: false, criteria: [] });
  try {
    const { data } = await sb
      .from("owner_decisions")
      .select("decided_at, action, target_id, note, payload")
      .eq("surface", "loopware_criteria")
      .order("id", { ascending: true })
      .limit(1000);
    const map = new Map<string, Criterion>();
    (data || []).forEach((r) => {
      const p = (r.payload || {}) as Record<string, string>;
      if (r.action === "criteria_revoked") map.delete(r.target_id);
      else
        map.set(r.target_id, {
          id: r.target_id,
          text: r.note || "",
          range: p.range || "",
          basis: p.basis || "",
          at: r.decided_at,
        });
    });
    return NextResponse.json({ ok: true, configured: true, criteria: [...map.values()].reverse() });
  } catch {
    return NextResponse.json({ ok: true, configured: false, criteria: [] });
  }
}

export async function POST(req: Request) {
  let b: { op?: string; id?: string; text?: string; range?: string; basis?: string; week?: string };
  try {
    b = await req.json();
  } catch {
    return NextResponse.json({ ok: false }, { status: 400 });
  }
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: true, persisted: false, reason: "supabase_unconfigured" });

  const review = b.op === "review";
  const action =
    b.op === "revoke" ? "criteria_revoked" : b.op === "edit" ? "criteria_edited" : review ? "review_done" : "criteria_approved";
  try {
    const { error } = await sb.from("owner_decisions").insert({
      surface: review ? "loopware_review" : "loopware_criteria",
      action,
      source: "app",
      employee: "312",
      target_type: review ? "loopware_week" : "loopware_criteria",
      target_id: review ? b.week || "-" : b.id || "-",
      subject: review ? `週次レビュー ${b.week || ""}` : (b.text || "").slice(0, 200),
      note: b.text || null,
      payload: { kind: "loopware", range: b.range || null, basis: b.basis || null, week: b.week || null },
    });
    if (error) return NextResponse.json({ ok: true, persisted: false, reason: error.message });
    return NextResponse.json({ ok: true, persisted: true });
  } catch (e) {
    return NextResponse.json({ ok: true, persisted: false, reason: e instanceof Error ? e.message : String(e) });
  }
}
