import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { alreadyLogged, applyViaDashboard, snoozeItem } from "@/lib/desk";
import { writeDecision } from "@/lib/ownerDecisionLog";
import { isDeskItemId, type NextEffect } from "@/lib/deskCore";
import type { Timing } from "@/lib/decisionContract";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Body = {
  itemId?: string;
  verdict?: "good" | "wrong";
  idemKey?: string;
  step?: { id?: string; text?: string; effect?: NextEffect };
  stayReason?: string | null;
  subject?: string;
  partner?: string;
  timing?: Timing;
};

/**
 * 残り案件の「次の一手」への 良い／違う。
 * 良い → そのとおりに動かす（後で3日／ToDo／見送り。返信は画面側で Jarvis を開く）
 * 違う → 記録だけ（型が外れた数を週次で数える）
 */
export async function POST(req: Request) {
  let b: Body;
  try {
    b = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }
  const id = String(b.itemId || "");
  const key = String(b.idemKey || "");
  const effect = b.step?.effect;
  if (!isDeskItemId(id) || !["good", "wrong"].includes(String(b.verdict)) || key.length < 8 || !b.step?.id) {
    return NextResponse.json({ ok: false, error: "itemId / verdict / idemKey / step" }, { status: 400 });
  }
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  if (await alreadyLogged(sb, key)) return NextResponse.json({ ok: true, duplicate: true });

  let done: string | null = null;
  if (b.verdict === "good") {
    if (effect === "snooze3") done = (await snoozeItem(sb, id, 3)) ? "snoozed" : null;
    else if (effect === "todo") done = (await applyViaDashboard(id, "todoist")).ok ? "todoist" : null;
    else if (effect === "skip") done = (await applyViaDashboard(id, "skip")).ok ? "skipped" : null;
    else if (effect === "reply") done = "reply_opened";
    if (!done) return NextResponse.json({ ok: false, error: "動かせませんでした（もう片付いているかもしれません）" }, { status: 409 });
  }

  const r = await writeDecision(sb, {
    surface: "triage",
    action: b.verdict === "good" ? "next_good" : "next_wrong",
    source: "loopware",
    targetType: "triage_item",
    targetId: id,
    employee: "116",
    subject: b.subject,
    partner: b.partner,
    idemKey: key,
    nextStep: `${b.step.id}: ${b.step.text || ""}`,
    stayReason: b.stayReason,
    timing: b.timing,
    payload: { next_step_id: b.step.id, next_effect: effect, done },
  });
  return NextResponse.json({ ok: r.ok, done, logged: r.ok && r.persisted });
}
