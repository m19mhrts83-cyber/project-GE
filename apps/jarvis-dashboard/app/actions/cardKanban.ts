"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { createNotionTask } from "@/lib/notionTasks";
import { queueLaneActionLog } from "@/lib/laneActionLog";

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
  const { data: card } = await supabase
    .from("cards")
    .select("id,lane,title")
    .eq("id", cardId)
    .maybeSingle();
  const { error } = await supabase
    .from("cards")
    .update({
      status: "archived",
      archived_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    })
    .eq("id", cardId);
  if (error) return { ok: false, error: error.message };
  if (card?.lane) {
    await queueLaneActionLog({
      lane: card.lane,
      event: "見送り",
      body: `- ${card.title || cardId}`,
      cardId,
    });
  }
  revalidatePath(path);
  return { ok: true, message: "スキップしました" };
}

export async function promoteCardToNotion(
  cardId: string,
  lane: string,
  path: string,
  opts?: { title?: string; summary?: string },
): Promise<CardActionResult> {
  const supabase = await createClient();
  const { data: card, error: gErr } = await supabase
    .from("cards")
    .select("id,title,summary,payload,status,kind")
    .eq("id", cardId)
    .maybeSingle();
  if (gErr) return { ok: false, error: gErr.message };
  if (!card) return { ok: false, error: "カードが見つかりません" };

  const payload = (card.payload || {}) as Record<string, unknown>;
  const due =
    typeof payload.suggested_due === "string" ? payload.suggested_due : null;

  const title = (opts?.title || card.title || "").trim() || card.title;
  let summary = (opts?.summary ?? card.summary ?? "").trim();
  if (!summary && Array.isArray(payload.bullets)) {
    summary = (payload.bullets as unknown[])
      .map((b) => String(b))
      .join("\n")
      .slice(0, 1800);
  }

  const created = await createNotionTask(lane, {
    title,
    summary: summary || undefined,
    due,
  });
  if (!created.ok) return { ok: false, error: created.error };

  const nextPayload = {
    ...payload,
    notion_url: created.url,
    notion_page_id: created.id,
    promoted_at: new Date().toISOString(),
    promoted_title: title,
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

  await queueLaneActionLog({
    lane,
    event: "タスク登録",
    body: `- ${title}\n- Notion: ${created.url}`,
    cardId,
  });

  revalidatePath(path);
  return {
    ok: true,
    message: "Notion にタスクを登録しました",
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
  const { data: card } = await supabase
    .from("cards")
    .select("lane,title")
    .eq("id", cardId)
    .maybeSingle();
  const { error } = await supabase.from("card_comments").insert({
    card_id: cardId,
    role: "user",
    body: text,
  });
  if (error) return { ok: false, error: error.message };
  if (card?.lane) {
    await queueLaneActionLog({
      lane: card.lane,
      event: "コメント",
      body: `- ${card.title || cardId}\n- ${text.slice(0, 500)}`,
      cardId,
    });
  }
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

  const { data: card, error: cErr } = await supabase
    .from("cards")
    .select("id,title,summary,lane,payload,kind,cursor_prompt")
    .eq("id", cardId)
    .maybeSingle();
  if (cErr) return { ok: false, error: cErr.message };
  if (!card) return { ok: false, error: "カードが見つかりません" };

  const { error: uErr } = await supabase.from("card_comments").insert({
    card_id: cardId,
    role: "user",
    body: text,
  });
  if (uErr) return { ok: false, error: uErr.message };

  const { data: recent } = await supabase
    .from("card_comments")
    .select("role,body,created_at")
    .eq("card_id", cardId)
    .order("created_at", { ascending: false })
    .limit(16);

  const payload =
    card.payload && typeof card.payload === "object"
      ? (card.payload as Record<string, unknown>)
      : {};
  const question =
    typeof payload.question === "string" ? payload.question : "";
  const bullets = Array.isArray(payload.bullets)
    ? (payload.bullets as unknown[]).map((b) => String(b)).slice(0, 20)
    : [];
  const thread = (recent || [])
    .slice()
    .reverse()
    .map((c) => `[${c.role}] ${c.body}`)
    .join("\n");

  const isDigest = card.kind === "digest";
  const prompt = [
    "あなたは Jarvis（秘書 AI）です。ダッシュボードの確認テーマ／処置カードについて、ユーザーと日本語で具体的に相談してください。",
    "推測で事実を捏造しない。過去コメントの文脈を踏まえる。",
    isDigest
      ? "これは確認テーマです。いきなり Notion 登録を急かさない。内容を整理し、タスクにするなら「案のタイトル・やること1〜3点・期限の目安」を提案する。ユーザーが納得したら「タスク化する」ボタンで Notion に載せる旨を伝える。"
      : "処置候補として助言し、次の一手を1つ提案する。",
    "返信は要点から。8行以内を目安。定型の『承知して Notion へ』だけで終わらない。",
    "",
    `【レーン】${card.lane}`,
    `【種類】${card.kind}`,
    `【タイトル】${card.title}`,
    question ? `【問い】${question}` : "",
    `【要約】\n${card.summary || "—"}`,
    bullets.length
      ? `【候補メモ】\n${bullets.map((l) => (l.startsWith("-") ? l : `- ${l}`)).join("\n")}`
      : "",
    card.cursor_prompt ? `【参考メモ】\n${String(card.cursor_prompt).slice(0, 800)}` : "",
    `【直近のやり取り】\n${thread || "（なし）"}`,
    "",
    `【今回のメッセージ】\n${text}`,
  ]
    .filter(Boolean)
    .join("\n");

  const { geminiReply } = await import("@/lib/geminiReply");
  const ai = await geminiReply(prompt);
  let reply: string;
  if (ai.ok) {
    reply = ai.text.slice(0, 2000);
  } else {
    reply = isDigest
      ? [
          "（自動応答が一時的に使えませんでした）",
          "この確認テーマでは、下のコメントで方針を相談したあと、納得したら「タスク化する」→ 内容確認 → Notion 登録、の流れです。",
          `いまのテーマ: ${card.title.replace(/^\[確認\]\s*/, "")}`,
          ai.error ? `詳細: ${ai.error}` : "",
        ]
          .filter(Boolean)
          .join("\n")
      : `（自動応答が使えませんでした）${ai.error || ""}「処置として進める」で Notion に載せられます。`;
  }

  const { error: jErr } = await supabase.from("card_comments").insert({
    card_id: cardId,
    role: "jarvis",
    body: reply,
  });
  if (jErr) return { ok: false, error: jErr.message };

  if (card.lane) {
    await queueLaneActionLog({
      lane: card.lane,
      event: "Jarvis相談",
      body: `- ${card.title || cardId}\n- Q: ${text.slice(0, 300)}\n- A: ${reply.slice(0, 500)}`,
      cardId,
    });
  }

  revalidatePath(path);
  return { ok: true, message: "Jarvis が返信しました" };
}
