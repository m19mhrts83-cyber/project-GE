import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { alreadyLogged } from "@/lib/desk";
import { markMiss } from "@/lib/misses";
import { writeDecision } from "@/lib/ownerDecisionLog";
import { isTriageItemId } from "@/lib/deskCore";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * 見落としの判断。miss=要対応だった（仕分けが外れた）／ok=出さなくてよい（仕分けが当たった）。
 * 判断ログは surface=triage_miss。action: wrong（仕分けが外れた）／good（当たった）
 */
export async function POST(req: Request) {
  let b: { itemId?: string; verdict?: string; idemKey?: string; why?: string; subject?: string; partner?: string; fromEmail?: string };
  try {
    b = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }
  const id = String(b.itemId || "");
  const key = String(b.idemKey || "");
  // 見落としには業者返信（re-vendor-…）も出るので、デスク用の isDeskItemId ではなく形だけ見る
  if (!isTriageItemId(id) || !["miss", "ok"].includes(String(b.verdict)) || key.length < 8) {
    return NextResponse.json({ ok: false, error: "itemId / verdict / idemKey" }, { status: 400 });
  }
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  if (await alreadyLogged(sb, key)) return NextResponse.json({ ok: true, duplicate: true });
  const isMiss = b.verdict === "miss";
  const m = await markMiss(sb, id, isMiss);
  const r = await writeDecision(sb, {
    surface: "triage_miss",
    action: isMiss ? "wrong" : "good",
    source: "loopware",
    targetType: "triage_item",
    targetId: id,
    employee: "116",
    subject: b.subject,
    partner: b.partner,
    idemKey: key,
    payload: { why: b.why || null, from_email: b.fromEmail || null, restored: m.restored },
  });
  return NextResponse.json({ ok: r.ok, restored: m.restored });
}
