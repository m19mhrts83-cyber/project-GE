import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import { RETRO_QUALITY, parseRetro } from "@/lib/kurashiftDecision";

/**
 * 後日の答え合わせ（ループウェア S21「使った結果を振り返る」）。
 * POST { kind: "money"|"deal", targetId, refId, quality: good|meh|regret, note? }
 * - 資金移動: assist_payload.decision_log の該当の判断（at=refId）に retro を足す
 * - 物件: kurashift_re_deal_events に note 行を足す（payload.action=retro, ref_event_id）
 * 元の判断は書き換えない（答え合わせは足すだけ）。
 */
export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const body = await req.json().catch(() => ({}));
  const kind = String(body.kind || "");
  const targetId = String(body.targetId || "");
  const refId = String(body.refId || "");
  const retro = parseRetro(body);
  if (!retro || !targetId || !refId || (kind !== "money" && kind !== "deal")) {
    return NextResponse.json({ error: "kind, targetId, refId, quality required" }, { status: 400 });
  }

  if (kind === "money") {
    const { data: row, error } = await supabase
      .from("kurashift_money_ops")
      .select("id, assist_payload")
      .eq("id", targetId)
      .maybeSingle();
    if (error || !row) {
      return NextResponse.json({ error: error?.message || "not found" }, { status: 404 });
    }
    const assist =
      row.assist_payload && typeof row.assist_payload === "object"
        ? { ...(row.assist_payload as Record<string, unknown>) }
        : {};
    const log = Array.isArray(assist.decision_log) ? [...assist.decision_log] : [];
    const idx = log.findIndex(
      (e) => e && typeof e === "object" && String((e as Record<string, unknown>).at || "") === refId
    );
    if (idx < 0) {
      return NextResponse.json({ error: "decision not found" }, { status: 404 });
    }
    log[idx] = { ...(log[idx] as Record<string, unknown>), retro };
    // last_decision は status 変化の印なので触らない（DB トリガーは last_retro を見る）
    const { error: upErr } = await supabase
      .from("kurashift_money_ops")
      .update({
        assist_payload: { ...assist, decision_log: log, last_retro: { ...retro, ref_at: refId } },
        updated_at: new Date().toISOString(),
      })
      .eq("id", targetId);
    if (upErr) {
      return NextResponse.json({ error: upErr.message }, { status: 500 });
    }
    return NextResponse.json({ ok: true, retro });
  }

  const { error: insErr } = await supabase.from("kurashift_re_deal_events").insert({
    deal_id: targetId,
    event_type: "note",
    actor: "user",
    summary: `答え合わせ: ${RETRO_QUALITY[retro.quality]}`,
    payload: {
      action: "retro",
      ref_event_id: refId,
      quality: retro.quality,
      note: retro.note,
      decided_by: user.email ?? user.id,
    },
  });
  if (insErr) {
    return NextResponse.json({ error: insErr.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, retro });
}
