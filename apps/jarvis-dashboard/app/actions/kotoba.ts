"use server";

/**
 * ことばの棚（/kotoba）での判断: 残す／いらない／迷う／ひとこと、と棚ごとのまとめ。
 * カードの状態は kotoba_cards.status に、判断そのものは owner_decisions（surface=kotoba）に残す。
 * 迷う・未判断は「いらない」に混ぜない（ループウェアの方針）。
 */
import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { createServiceClient } from "@/lib/supabase/admin";
import { normalizeDecision } from "@/lib/decisionContract";
import { VERDICT, isCardId, isShelf, type KotobaVerdict } from "@/lib/kotoba";

export type KotobaResult = { ok: true; duplicate: boolean } | { ok: false; error: string };

async function signedIn(): Promise<boolean> {
  const auth = await createClient();
  const {
    data: { user },
  } = await auth.auth.getUser();
  return Boolean(user);
}

export async function judgeKotoba(
  cardId: string,
  verdict: KotobaVerdict,
  idemKey: string,
  note?: string,
): Promise<KotobaResult> {
  if (!(await signedIn())) return { ok: false, error: "ログインが切れています" };
  if (!(verdict in VERDICT)) return { ok: false, error: "判断の種類が不正です" };
  if (!isCardId(cardId)) return { ok: false, error: "カードが不正です" };
  if (String(idemKey || "").length < 8) return { ok: false, error: "idemKey" };
  const text = String(note || "").trim().slice(0, 2000);
  if (verdict === "comment" && !text) return { ok: false, error: "ひとことが空です" };

  const sb = createServiceClient();
  if (!sb) return { ok: false, error: "Supabase が未設定です" };

  // 判断ログに写す中身は画面からではなく DB のカードから取る
  const { data: card, error: readErr } = await sb
    .from("kotoba_cards")
    .select("id,body,speaker,where_label,kind,shelves,status,source,source_ref")
    .eq("id", cardId)
    .maybeSingle();
  if (readErr) return { ok: false, error: `読み込みに失敗: ${readErr.message}` };
  if (!card) return { ok: false, error: "カードが見つかりません" };

  const v = VERDICT[verdict];
  const n = normalizeDecision({
    surface: "kotoba",
    action: v.action,
    source: "dashboard",
    targetType: "kotoba_card",
    targetId: cardId,
    idemKey,
    subject: String(card.body).slice(0, 200),
    partner: card.speaker || null,
    note: text || null,
    payload: {
      card_id: cardId,
      kind: card.kind,
      shelves: card.shelves,
      from_status: card.status,
      to_status: v.status,
      card_source: card.source,
      source_detail: "dashboard_kotoba",
    },
  });
  if (!n.ok) return { ok: false, error: n.error };

  const { data: dup } = await sb
    .from("owner_decisions")
    .select("id")
    .eq("payload->>idem_key", n.idemKey)
    .limit(1)
    .maybeSingle();
  if (dup) return { ok: true, duplicate: true };

  if (v.status) {
    const now = new Date().toISOString();
    const { error } = await sb
      .from("kotoba_cards")
      .update({ status: v.status, decided_at: now, updated_at: now })
      .eq("id", cardId);
    if (error) return { ok: false, error: `更新に失敗: ${error.message}` };
  }
  if (text) {
    const { error } = await sb.from("kotoba_notes").insert({ card_id: cardId, kind: "comment", body: text });
    if (error) return { ok: false, error: `ひとことの保存に失敗: ${error.message}` };
  }

  const { error } = await sb.from("owner_decisions").insert(n.row);
  if (error && error.code !== "23505") console.warn(`owner_decisions soft-fail: ${error.message}`);
  revalidatePath("/kotoba");
  return { ok: true, duplicate: Boolean(error) };
}

/** 棚ごとのまとめ・感想（月初の振り返りの材料） */
export async function addShelfNote(shelf: string, body: string): Promise<KotobaResult> {
  if (!(await signedIn())) return { ok: false, error: "ログインが切れています" };
  if (!isShelf(shelf)) return { ok: false, error: "棚が不正です" };
  const text = String(body || "").trim().slice(0, 4000);
  if (!text) return { ok: false, error: "まとめが空です" };
  const sb = createServiceClient();
  if (!sb) return { ok: false, error: "Supabase が未設定です" };
  const { error } = await sb.from("kotoba_notes").insert({ shelf, kind: "summary", body: text });
  if (error) return { ok: false, error: `保存に失敗: ${error.message}` };
  revalidatePath("/kotoba");
  return { ok: true, duplicate: false };
}
