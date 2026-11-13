import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { savePolicy } from "@/lib/senderPolicy";
import { writeDecision } from "@/lib/ownerDecisionLog";
import { isDeskItemId } from "@/lib/deskCore";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const DAYS = 7;

/** 「出さずに自動で回答不要」にした送り手のメールで、直近7日に自動で閉じたもの */
export async function GET() {
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: true, items: [] });
  const since = new Date(Date.now() - DAYS * 86400_000).toISOString();
  const { data, error } = await sb
    .from("triage_items")
    .select("id,subject,partner,from_email,updated_at")
    .eq("status", "done")
    .filter("payload->loopware_auto_policy->>source", "eq", "auto_policy")
    .gte("updated_at", since)
    .order("updated_at", { ascending: false })
    .limit(50);
  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  return NextResponse.json(
    {
      ok: true,
      items: (data || []).map((r) => ({
        id: String(r.id),
        subject: String(r.subject || ""),
        who: String(r.partner || r.from_email || ""),
        at: String(r.updated_at || ""),
      })),
    },
    { headers: { "cache-control": "private, no-store" } },
  );
}

/** 戻す: 未判断に戻し、その送り手は「毎回見る」にする（また自動で閉じないように） */
export async function POST(req: Request) {
  let b: { itemId?: string; idemKey?: string };
  try {
    b = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }
  const id = String(b.itemId || "");
  const idemKey = String(b.idemKey || "").slice(0, 200);
  if (!isDeskItemId(id) || idemKey.length < 8) {
    return NextResponse.json({ ok: false, error: "itemId / idemKey" }, { status: 400 });
  }
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  const { data: row } = await sb
    .from("triage_items")
    .select("status,payload,from_email,subject,partner,lane")
    .eq("id", id)
    .maybeSingle();
  const pl = { ...((row?.payload as Record<string, unknown>) || {}) };
  if (!row || row.status !== "done" || !pl.loopware_auto_policy) {
    return NextResponse.json({ ok: false, error: "自動で閉じたメールではありません" }, { status: 404 });
  }
  delete pl.loopware_auto_policy;
  delete pl.loopware_action;
  pl.loopware_auto_undone_at = new Date().toISOString();
  const { error } = await sb
    .from("triage_items")
    .update({ status: "pending", payload: pl, updated_at: new Date().toISOString() })
    .eq("id", id);
  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  if (row.from_email) await savePolicy(sb, String(row.from_email), "always");
  await writeDecision(sb, {
    surface: "triage",
    action: "wrong",
    source: "loopware",
    targetType: "triage_item",
    targetId: id,
    employee: "116",
    subject: row.subject,
    partner: row.partner,
    lane: row.lane,
    idemKey,
    note: "自動で回答不要にしたのを戻した（この送り手は毎回見るに変更）",
  });
  return NextResponse.json({ ok: true });
}
