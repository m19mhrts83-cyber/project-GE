"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { createServiceClient } from "@/lib/supabase/admin";
import { applyS9Action, type S9Decision } from "@/lib/s9SlackAction";
import { normName, parseSnapshot } from "@/lib/grokCandidates";

export type GrokDecideResult = { ok: boolean; message: string };

/**
 * Grok 候補の「採用／見送り」。Slack の［採用］［見送り］と同じ道（kurashift_jobs → Mac worker → 台帳 → 送信キュー）。
 * ここでは送信しない。送信は従来どおり 311 ゲートと本人了承。
 * 候補の中身はブラウザから受け取らず、スナップショットから名前で引き直す（改ざん・古い画面対策）。
 */
export async function decideGrokCandidate(
  name: string,
  decision: S9Decision,
): Promise<GrokDecideResult> {
  if (decision !== "adopt" && decision !== "skip") {
    return { ok: false, message: "判断が不正です" };
  }
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { ok: false, message: "ログインが必要です" };

  const sb = createServiceClient();
  if (!sb) return { ok: false, message: "Supabase が未設定です" };
  const { data: meta } = await sb
    .from("sync_meta")
    .select("value")
    .eq("key", "grok_candidates_snapshot")
    .maybeSingle();
  const snap = parseSnapshot(meta?.value);
  const key = normName(name);
  const item = snap?.items.find((i) => i.kind === "consult" && normName(i.cand.name) === key);
  if (!item) return { ok: false, message: "判断待ちの候補が見つかりません（画面を更新してください）" };

  // 台帳に入っている＝もう判断済み。二重に積まない
  const { data: led } = await sb
    .from("kurashift_re_mgmt_vendors")
    .select("name,status")
    .limit(2000);
  if ((led || []).some((r) => normName(String(r.name || "")) === key)) {
    return { ok: true, message: "すでに台帳にあります（判断済み）" };
  }

  const r = await applyS9Action({
    decision,
    candidate: item.cand,
    source: "dashboard",
    userId: user.id,
  });
  revalidatePath("/grok-candidates");
  return { ok: r.ok, message: r.message };
}
