/**
 * 113 物件買進め確認係 — #deal-active「どうしますか？」ボタンの受け口。
 *
 * 続ける: 次に聞く日 +14日／保留: +30日／見送り: KURASHIFT status=passed＋クローズ／完了: クローズ
 * 状態は kurashift_re_deals.summary_json.slack_deal_active に持つ（migration 不要）。
 * 親メッセージの「クローズ」表示と7日後の削除は scripts/kurashift_deal_active_113.py が行う。
 * 対外送信はしない。
 */
import { createServiceClient } from "@/lib/supabase/admin";
import { logOwnerDecision } from "@/lib/ownerDecisionLog";
import {
  D113_ICON,
  D113_LABEL,
  jstToday,
  nextD113State,
  parseD113ButtonValue,
  replaceDecidedRow,
  type D113State,
} from "@/lib/dealActive113Core";

export { parseD113ButtonValue };

export type D113Result =
  | { kind: "ok"; text: string; blocks: Array<Record<string, unknown>> }
  | { kind: "error"; text: string };

export async function handleD113BlockAction(opts: {
  value: string;
  blocks: Array<Record<string, unknown>>;
  userId: string;
}): Promise<D113Result | null> {
  const parsed = parseD113ButtonValue(opts.value);
  if (!parsed) return null;
  const { action, dealId } = parsed;
  const sb = createServiceClient();
  if (!sb) return { kind: "error", text: "Service Role 未設定のため反映できませんでした" };

  const { data: row, error } = await sb
    .from("kurashift_re_deals")
    .select("id, title, status, summary_json")
    .eq("id", dealId)
    .maybeSingle();
  if (error || !row) {
    return { kind: "error", text: `案件が見つかりませんでした（${dealId}）` };
  }
  const sj = (row.summary_json && typeof row.summary_json === "object"
    ? row.summary_json
    : {}) as Record<string, unknown>;
  const st = (sj.slack_deal_active || {}) as D113State;
  const today = jstToday();
  const next = nextD113State(st, action, today);

  const patch: Record<string, unknown> = {
    summary_json: { ...sj, slack_deal_active: next },
  };
  const fromStatus = String(row.status || "");
  if (action === "pass" && fromStatus !== "passed") {
    patch.status = "passed";
  }
  const { error: upErr } = await sb.from("kurashift_re_deals").update(patch).eq("id", dealId);
  if (upErr) {
    return { kind: "error", text: `KURASHIFT への反映に失敗しました: ${upErr.message.slice(0, 120)}` };
  }

  // 判断履歴（best-effort）
  try {
    await sb.from("kurashift_re_deal_events").insert({
      deal_id: dealId,
      event_type: action === "pass" ? "status_change" : "note",
      actor: "matsuno_slack",
      summary: `#deal-active ${D113_LABEL[action]}`,
      from_status: action === "pass" ? fromStatus : null,
      to_status: action === "pass" ? "passed" : null,
      payload: { source: "deal_active_113", action },
      occurred_at: new Date().toISOString(),
    });
  } catch {
    /* 表が無くても本線は止めない */
  }
  await logOwnerDecision({
    surface: "deal_active_113",
    action,
    source: "slack_button",
    employee: "113",
    targetType: "deal",
    targetId: dealId,
    subject: String(row.title || "").slice(0, 200),
  });

  const title = String(row.title || dealId).slice(0, 40);
  return {
    kind: "ok",
    text: `${D113_ICON[action]} ${title}: ${D113_LABEL[action]}`,
    blocks: replaceDecidedRow(opts.blocks, dealId, action, opts.userId),
  };
}
