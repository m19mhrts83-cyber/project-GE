import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { alreadyLogged, applyViaDashboard, enrichTriggerRow, markHesitated } from "@/lib/desk";
import { writeDecision } from "@/lib/ownerDecisionLog";
import { CHOICE_ACTION, CHOICE_MA, DESK_CHOICES, isDeskItemId, type DeskChoice } from "@/lib/deskCore";
import type { Timing } from "@/lib/decisionContract";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Body = {
  itemId?: string;
  choice?: string;
  idemKey?: string;
  reasonTags?: string[];
  stayReason?: string | null;
  note?: string | null;
  timing?: Timing;
  subject?: string;
  partner?: string;
  lane?: string;
  appliedRules?: string[];
};

/** 判断デスクの1判断。同じ idemKey の再送は何もしないで ok を返す */
export async function POST(req: Request) {
  let b: Body;
  try {
    b = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }
  const id = String(b.itemId || "");
  const choice = String(b.choice || "") as DeskChoice;
  const idemKey = String(b.idemKey || "").slice(0, 200);
  if (!isDeskItemId(id) || !(DESK_CHOICES as readonly string[]).includes(choice) || idemKey.length < 8) {
    return NextResponse.json({ ok: false, error: "itemId / choice / idemKey" }, { status: 400 });
  }
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });

  if (await alreadyLogged(sb, idemKey)) return NextResponse.json({ ok: true, duplicate: true });

  const base = {
    surface: "triage",
    action: CHOICE_ACTION[choice],
    source: "loopware",
    targetType: "triage_item",
    targetId: id,
    employee: "116",
    subject: b.subject,
    partner: b.partner,
    lane: b.lane,
    idemKey,
    reasonTags: b.reasonTags,
    stayReason: b.stayReason,
    note: b.note,
    timing: b.timing,
    appliedRules: b.appliedRules,
  };

  // 迷った: 状態は変えない（NG に混ぜない）。判断ログに1行と、デスクで後ろへ回す印
  if (choice === "hesitate") {
    const r = await writeDecision(sb, base);
    if (!r.ok) return NextResponse.json(r, { status: 400 });
    await markHesitated(sb, id, b.timing);
    return NextResponse.json({ ok: true, logged: r.persisted });
  }

  const ma = CHOICE_MA[choice];
  if (!ma) return NextResponse.json({ ok: false, error: "choice" }, { status: 400 });
  const res = await applyViaDashboard(id, ma);
  if (!res.ok) return NextResponse.json({ ok: false, error: res.message || "Jarvis 側で失敗しました" }, { status: 502 });
  try {
    const e = await enrichTriggerRow(sb, base);
    return NextResponse.json({ ok: true, message: res.message, logged: e.via });
  } catch (e) {
    // 状態は変わった。ログの足し込みだけ失敗
    return NextResponse.json({ ok: true, message: res.message, logged: false, reason: e instanceof Error ? e.message : String(e) });
  }
}
