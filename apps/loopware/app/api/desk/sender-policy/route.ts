import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { savePolicy } from "@/lib/senderPolicy";
import { SENDER_POLICIES, isPolicy, senderKey } from "@/lib/senderPolicyCore";
import { writeDecision } from "@/lib/ownerDecisionLog";
import { isDeskItemId } from "@/lib/deskCore";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** 判断のあとに選ぶ「この送り手は次回から」。1送り手1設定（あとから変えれば上書き） */
export async function POST(req: Request) {
  let b: { itemId?: string; policy?: string; idemKey?: string };
  try {
    b = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }
  const id = String(b.itemId || "");
  const idemKey = String(b.idemKey || "").slice(0, 200);
  if (!isDeskItemId(id) || !isPolicy(b.policy) || idemKey.length < 8) {
    return NextResponse.json({ ok: false, error: "itemId / policy / idemKey" }, { status: 400 });
  }
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  const { data: row } = await sb.from("triage_items").select("from_email,subject,partner,lane").eq("id", id).maybeSingle();
  const key = senderKey(row?.from_email);
  if (!row || !key) return NextResponse.json({ ok: false, error: "送り手のアドレスが取れません" }, { status: 404 });
  if (!(await savePolicy(sb, String(row.from_email), b.policy))) {
    return NextResponse.json({ ok: false, error: "保存できませんでした" }, { status: 500 });
  }
  // 判断ログにも1行（週次分析がルール候補の根拠にする）
  await writeDecision(sb, {
    surface: "triage",
    action: "comment",
    source: "loopware",
    targetType: "triage_item",
    targetId: id,
    employee: "116",
    subject: row.subject,
    partner: row.partner,
    lane: row.lane,
    idemKey: `${idemKey}:sender`,
    note: `この送り手は次回から「${SENDER_POLICIES[b.policy]}」（${key}）`,
  });
  return NextResponse.json({ ok: true });
}
