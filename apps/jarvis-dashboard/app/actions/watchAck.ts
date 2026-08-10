"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import {
  WATCH_ACK_QUIET_DAYS_DEFAULT,
  buildWatchAckFingerprint,
  quietUntilIso,
  usesSpecializedAck,
} from "@/lib/watchUserAck";

export type WatchAckResult = { ok: boolean; error?: string; message?: string };

function quietDays(): number {
  const raw = process.env.JARVIS_WATCH_ACK_QUIET_DAYS;
  const n = raw ? Number(raw) : NaN;
  return Number.isFinite(n) && n >= 1 ? Math.floor(n) : WATCH_ACK_QUIET_DAYS_DEFAULT;
}

/**
 * 汎用「確認した」。バッジ／ナビを一時抑制。
 * 指紋変化 or quiet_until 超過で再表示（Mac push がマージ）。
 */
export async function acknowledgeWatch(id: string): Promise<WatchAckResult> {
  const watchId = String(id || "").trim();
  if (!watchId) return { ok: false, error: "id が空です" };
  if (usesSpecializedAck(watchId)) {
    return { ok: false, error: "この項目は専用の確認ボタンを使ってください" };
  }

  const supabase = await createClient();
  const { data: row, error } = await supabase
    .from("watch_status")
    .select("id,level,summary,status,payload")
    .eq("id", watchId)
    .maybeSingle();
  if (error) return { ok: false, error: error.message };
  if (!row) return { ok: false, error: "ウォッチが見つかりません" };

  const level = String(row.level || "");
  if (level !== "attention" && level !== "warn") {
    return { ok: false, error: "要確認／注意のときだけ確認できます" };
  }

  const payload =
    row.payload && typeof row.payload === "object"
      ? ({ ...(row.payload as Record<string, unknown>) } as Record<string, unknown>)
      : {};

  const fingerprint = buildWatchAckFingerprint({
    id: watchId,
    level: row.level,
    summary: row.summary,
    payload,
  });
  const now = new Date();
  const user_ack = {
    fingerprint,
    acked_at: now.toISOString(),
    quiet_until: quietUntilIso(quietDays(), now),
    acked_level: level,
  };
  payload.user_ack = user_ack;
  payload.show_banner = false;
  payload.badge_suppressed = true;

  const { error: upErr } = await supabase
    .from("watch_status")
    .update({
      payload,
      updated_at: now.toISOString(),
    })
    .eq("id", watchId);
  if (upErr) return { ok: false, error: upErr.message };

  revalidatePath("/");
  revalidatePath("/situation");
  revalidatePath("/openchat");
  revalidatePath("/openchat/health");
  return {
    ok: true,
    message: `確認済（${user_ack.quiet_until.slice(0, 10)}までバッジ抑制）`,
  };
}
