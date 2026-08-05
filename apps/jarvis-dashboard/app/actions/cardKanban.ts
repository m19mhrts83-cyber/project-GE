"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import { createNotionTask, loadNotionLaneConfig } from "@/lib/notionTasks";
import { queueLaneActionLog } from "@/lib/laneActionLog";
import {
  formatAskReplyBody,
  resolveAskReply,
  type AskEngine,
} from "@/lib/askEngine";
import {
  buildLocalHandoffPrompt,
  type CursorAskState,
} from "@/lib/localHandoff";
import { buildAskContextBundle } from "@/lib/askContextBundle";
export type CardActionResult = {
  ok: boolean;
  error?: string;
  message?: string;
  notionUrl?: string;
  fallbackNotices?: string[];
  localPrompt?: string;
  needLocal?: boolean;
  via?: string;
  queued?: boolean;
};

function asPayload(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" ? ({ ...v } as Record<string, unknown>) : {};
}

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
  opts?: { title?: string; summary?: string; propertyName?: string },
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

  const propertyName = (opts?.propertyName || "").trim() || null;
  const cfg = loadNotionLaneConfig(lane);
  if (cfg?.property_prop && !propertyName) {
    return { ok: false, error: "物件名（サブグループ）を選択してください" };
  }

  const created = await createNotionTask(lane, {
    title,
    summary: summary || undefined,
    due,
    propertyName,
  });
  if (!created.ok) return { ok: false, error: created.error };

  const nextPayload = {
    ...payload,
    notion_url: created.url,
    notion_page_id: created.id,
    promoted_at: new Date().toISOString(),
    promoted_title: title,
    notion_property_name: propertyName,
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
    body: `- ${title}\n- 物件名: ${propertyName || "—"}\n- Notion: ${created.url}`,
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

function cardHandoffFromRow(
  card: {
    id: string;
    title: string;
    summary: string | null;
    lane: string | null;
    payload: unknown;
    cursor_prompt: string | null;
  },
  comments: { role: string; body: string }[],
  lastUserMessage: string,
  extraNote?: string,
): string {
  const payload = asPayload(card.payload);
  const question =
    typeof payload.question === "string" ? payload.question : "";
  const bullets = Array.isArray(payload.bullets)
    ? (payload.bullets as unknown[]).map((b) => String(b)).slice(0, 20)
    : [];
  return buildLocalHandoffPrompt({
    kind: "card",
    id: card.id,
    title: card.title,
    summary: card.summary,
    question,
    bullets,
    lane: card.lane,
    cursorPrompt: card.cursor_prompt,
    comments,
    lastUserMessage,
    extraNote,
  });
}

export async function askJarvisOnCard(
  cardId: string,
  body: string,
  path: string,
  engine: AskEngine = "cursor",
  opts?: {
    useKamiooyaKnowledge?: boolean;
    useOnedriveYoritoori?: boolean;
    useGdrive?: boolean;
  },
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

  const payload = asPayload(card.payload);
  const question =
    typeof payload.question === "string" ? payload.question : "";
  const bullets = Array.isArray(payload.bullets)
    ? (payload.bullets as unknown[]).map((b) => String(b)).slice(0, 20)
    : [];
  const threadRows = (recent || []).slice().reverse();
  const thread = threadRows
    .map((c) => `[${c.role}] ${c.body}`)
    .join("\n");

  const isDigest = card.kind === "digest";
  const ctxQuery = [text, card.title, question, ...bullets.slice(0, 5)]
    .filter(Boolean)
    .join("\n")
    .slice(0, 1200);
  const ctx = await buildAskContextBundle({
    lane: card.lane,
    title: card.title,
    summary: card.summary,
    payload,
    query: ctxQuery,
    sources: {
      kamiooya: opts?.useKamiooyaKnowledge,
      onedriveYoritoori: opts?.useOnedriveYoritoori,
      gdrive: opts?.useGdrive,
    },
  });
  const knowledgeNotices = ctx.notices;
  const knowledgeBlock = ctx.promptBlock;

  const prompt = [
    "あなたは Jarvis（秘書 AI）です。ダッシュボードの確認テーマ／処置カードについて、ユーザーと日本語で具体的に相談してください。",
    "推測で事実を捏造しない。過去コメントの文脈を踏まえる。",
    isDigest
      ? "これは確認テーマです。いきなり Notion 登録を急かさない。内容を整理し、タスクにするなら「案のタイトル・やること1〜3点・期限の目安」を提案する。ユーザーが納得したら「タスク化する」ボタンで Notion に載せる旨を伝える。"
      : "処置候補として助言し、次の一手を1つ提案する。",
    "返信は要点から。8行以内を目安。定型の『承知して Notion へ』だけで終わらない。",
    knowledgeBlock
      ? "外部根拠（神大家DB／OneDriveやり取り／Drive NotebookLM）がある場合はそれを優先し、無いことは推測しない。"
      : "",
    "",
    `【レーン】${card.lane}`,
    `【種類】${card.kind}`,
    `【タイトル】${card.title}`,
    question ? `【問い】${question}` : "",
    `【要約】\n${card.summary || "—"}`,
    bullets.length
      ? `【候補メモ】\n${bullets.map((l) => (l.startsWith("-") ? l : `- ${l}`)).join("\n")}`
      : "",
    card.cursor_prompt
      ? `【参考メモ】\n${String(card.cursor_prompt).slice(0, 800)}`
      : "",
    knowledgeBlock,
    `【直近のやり取り】\n${thread || "（なし）"}`,
    "",
    `【今回のメッセージ】\n${text}`,
  ]
    .filter(Boolean)
    .join("\n");

  const localPrompt = [
    cardHandoffFromRow(
      card,
      threadRows.map((c) => ({ role: c.role, body: c.body })),
      text,
    ),
    knowledgeBlock,
  ]
    .filter(Boolean)
    .join("\n\n");

  const resolved = await resolveAskReply({ engine, prompt });
  if (!resolved.ok) {
    revalidatePath(path);
    return {
      ok: false,
      needLocal: true,
      error: resolved.error,
      fallbackNotices: [...knowledgeNotices, ...resolved.fallbackNotices],
      localPrompt,
      message: [...knowledgeNotices, ...resolved.fallbackNotices].join(" / "),
    };
  }

  const reply = formatAskReplyBody(
    resolved.text,
    resolved.via,
    resolved.fallbackNotices,
  );

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
      body: `- ${card.title || cardId}\n- via: ${resolved.via}\n- Q: ${text.slice(0, 300)}\n- A: ${reply.slice(0, 500)}`,
      cardId,
    });
  }

  revalidatePath(path);
  const allNotices = [...knowledgeNotices, ...resolved.fallbackNotices];
  const noticeMsg =
    allNotices.length > 0
      ? allNotices.join(" → ")
      : resolved.via === "cloud"
        ? "Jarvis Cloud が返信しました"
        : "Gemini が返信しました";
  return {
    ok: true,
    message: noticeMsg,
    fallbackNotices: allNotices,
    via: resolved.via,
    localPrompt,
  };
}

export async function enqueueCardCursorAsk(
  cardId: string,
  path: string,
  opts?: { extraNote?: string; question?: string },
): Promise<CardActionResult> {
  const supabase = await createClient();
  const { data: card, error: cErr } = await supabase
    .from("cards")
    .select("id,title,summary,lane,payload,cursor_prompt")
    .eq("id", cardId)
    .maybeSingle();
  if (cErr) return { ok: false, error: cErr.message };
  if (!card) return { ok: false, error: "カードが見つかりません" };

  const payload = asPayload(card.payload);
  const prev = payload.cursor_ask as CursorAskState | undefined;
  if (prev?.status === "queued" || prev?.status === "running") {
    return {
      ok: true,
      queued: true,
      message: "Mac のローカル Cursor への依頼は処理中です",
      fallbackNotices: ["すでに Mac へ依頼済みです。完了までお待ちください"],
    };
  }

  const { data: recent } = await supabase
    .from("card_comments")
    .select("role,body")
    .eq("card_id", cardId)
    .order("created_at", { ascending: false })
    .limit(16);
  const comments = (recent || []).slice().reverse();
  const question =
    (opts?.question || "").trim() ||
    [...comments].reverse().find((c) => c.role === "user")?.body ||
    "";

  const prompt = cardHandoffFromRow(
    card,
    comments,
    question,
    opts?.extraNote,
  );

  const cursorAsk: CursorAskState = {
    status: "queued",
    prompt,
    question,
    requested_at: new Date().toISOString(),
    via: "local_worker",
  };
  const nextPayload = { ...payload, cursor_ask: cursorAsk };
  const { error } = await supabase
    .from("cards")
    .update({
      payload: nextPayload,
      updated_at: new Date().toISOString(),
    })
    .eq("id", cardId);
  if (error) return { ok: false, error: error.message };

  revalidatePath(path);
  return {
    ok: true,
    queued: true,
    message:
      "Mac のローカル Cursor に依頼しました（Mac 起動後に返答が付きます）",
    fallbackNotices: [
      "Mac のローカル Cursor に依頼しました（起動後に返答が付きます）",
    ],
    localPrompt: prompt,
  };
}

export async function getCardCursorAskStatus(
  cardId: string,
): Promise<CardActionResult & { ask?: CursorAskState | null }> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("cards")
    .select("payload")
    .eq("id", cardId)
    .maybeSingle();
  if (error) return { ok: false, error: error.message };
  const payload = asPayload(data?.payload);
  const ask =
    payload.cursor_ask && typeof payload.cursor_ask === "object"
      ? (payload.cursor_ask as CursorAskState)
      : null;
  return { ok: true, ask };
}
