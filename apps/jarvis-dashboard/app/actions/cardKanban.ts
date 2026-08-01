"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { createNotionTask } from "@/lib/notionTasks";

export type CardActionResult = {
  ok: boolean;
  error?: string;
  message?: string;
  notionUrl?: string;
};

export async function skipCard(
  cardId: string,
  path: string,
): Promise<CardActionResult> {
  const supabase = await createClient();
  const { error } = await supabase
    .from("cards")
    .update({
      status: "archived",
      archived_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })
    .eq("id", cardId);
  if (error) return { ok: false, error: error.message };
  revalidatePath(path);
  return { ok: true, message: "スキップしました" };
}

export async function promoteCardToNotion(
  cardId: string,
  lane: string,
  path: string,
): Promise<CardActionResult> {
  const supabase = await createClient();
  const { data: card, error: gErr } = await supabase
    .from("cards")
    .select("id,title,summary,payload,status")
    .eq("id", cardId)
    .maybeSingle();
  if (gErr) return { ok: false, error: gErr.message };
  if (!card) return { ok: false, error: "カードが見つかりません" };

  const payload = (card.payload || {}) as Record<string, unknown>;
  const due =
    typeof payload.suggested_due === "string" ? payload.suggested_due : null;

  const created = await createNotionTask(lane, {
    title: card.title,
    summary: card.summary || undefined,
    due,
  });
  if (!created.ok) return { ok: false, error: created.error };

  const nextPayload = {
    ...payload,
    notion_url: created.url,
    notion_page_id: created.id,
    promoted_at: new Date().toISOString(),
  };
  const { error: uErr } = await supabase
    .from("cards")
    .update({
      status: "promoted",
      payload: nextPayload,
      updated_at: new Date().toISOString(),
    })
    .eq("id", cardId);
  if (uErr) return { ok: false, error: uErr.message };

  revalidatePath(path);
  return {
    ok: true,
    message: "Notion に追加しました",
    notionUrl: created.url,
  };
}

export async function postCardComment(
  cardId: string,
  body: string,
  path: string,
): Promise<CardActionResult> {
  const text = body.trim();
  if (!text) return { ok: false, error: "コメントを入力してください" };
  const supabase = await createClient();
  const { error } = await supabase.from("card_comments").insert({
    card_id: cardId,
    role: "user",
    body: text,
  });
  if (error) return { ok: false, error: error.message };
  revalidatePath(path);
  return { ok: true, message: "コメントを保存しました" };
}

export async function askJarvisOnCard(
  cardId: string,
  body: string,
  path: string,
): Promise<CardActionResult> {
  const text = body.trim();
  if (!text) return { ok: false, error: "質問を入力してください" };
  const supabase = await createClient();
  const { error: uErr } = await supabase.from("card_comments").insert({
    card_id: cardId,
    role: "user",
    body: text,
  });
  if (uErr) return { ok: false, error: uErr.message };

  const { data: card } = await supabase
    .from("cards")
    .select("title,summary,lane,payload")
    .eq("id", cardId)
    .maybeSingle();

  let reply =
    "（メモ）処置候補として保持されています。「処置として進める」で Notion 看板に載せられます。";
  const key = (process.env.GEMINI_API_KEY || "").trim();
  if (key && card) {
    try {
      const prompt = [
        "あなたは Jarvis。ダッシュボードの処置候補カードについて短く日本語で助言してください。",
        `レーン: ${card.lane}`,
        `タイトル: ${card.title}`,
        `要約: ${card.summary || ""}`,
        `ユーザー: ${text}`,
        "返信は5行以内。次の一手を1つ提案。",
      ].join("\n");
      const res = await fetch(
        `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${key}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            contents: [{ parts: [{ text: prompt }] }],
          }),
        },
      );
      if (res.ok) {
        const j = (await res.json()) as {
          candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }>;
        };
        const t = j.candidates?.[0]?.content?.parts?.[0]?.text?.trim();
        if (t) reply = t.slice(0, 1200);
      }
    } catch {
      /* keep fallback */
    }
  }

  const { error: jErr } = await supabase.from("card_comments").insert({
    card_id: cardId,
    role: "jarvis",
    body: reply,
  });
  if (jErr) return { ok: false, error: jErr.message };
  revalidatePath(path);
  return { ok: true, message: "Jarvis が返信しました" };
}
