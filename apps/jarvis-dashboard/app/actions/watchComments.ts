"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
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

export type WatchCommentActionResult = {
  ok: boolean;
  error?: string;
  message?: string;
  fallbackNotices?: string[];
  localPrompt?: string;
  needLocal?: boolean;
  via?: string;
  queued?: boolean;
};

function asPayload(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" ? ({ ...v } as Record<string, unknown>) : {};
}

export async function postWatchComment(
  watchId: string,
  body: string,
  path = "/situation",
): Promise<WatchCommentActionResult> {
  const text = body.trim();
  if (!text) return { ok: false, error: "コメントが空です" };
  const supabase = await createClient();
  const { error } = await supabase.from("watch_comments").insert({
    watch_id: watchId,
    role: "user",
    body: text,
  });
  if (error) return { ok: false, error: error.message };
  revalidatePath(path);
  revalidatePath("/");
  return { ok: true, message: "コメントを投稿しました" };
}

export async function askJarvisOnWatch(
  watchId: string,
  body: string,
  path = "/situation",
  engine: AskEngine = "cursor",
  opts?: {
    useKamiooyaKnowledge?: boolean;
    useOnedriveYoritoori?: boolean;
    useGdrive?: boolean;
  },
): Promise<WatchCommentActionResult> {
  const question = body.trim();
  if (!question) return { ok: false, error: "質問が空です" };

  const supabase = await createClient();

  const { data: watch, error: wErr } = await supabase
    .from("watch_status")
    .select("id,title,summary,detail,level,payload,cursor_prompt")
    .eq("id", watchId)
    .maybeSingle();
  if (wErr) return { ok: false, error: wErr.message };
  if (!watch) return { ok: false, error: "ウォッチ項目が見つかりません" };

  const { error: uErr } = await supabase.from("watch_comments").insert({
    watch_id: watchId,
    role: "user",
    body: question,
  });
  if (uErr) return { ok: false, error: uErr.message };

  const { data: recent } = await supabase
    .from("watch_comments")
    .select("role,body,created_at")
    .eq("watch_id", watchId)
    .order("created_at", { ascending: false })
    .limit(12);

  const payload = asPayload(watch.payload);
  const actions = Array.isArray(payload.actions) ? payload.actions : [];
  const actionLines = actions
    .slice(0, 20)
    .map((a) => {
      if (!a || typeof a !== "object") return "";
      const row = a as Record<string, unknown>;
      return String(
        row.line ||
          `${row.date} / ${row.shop} / ¥${row.amount} / ${row.proposal || ""}`,
      );
    })
    .filter(Boolean);

  const threadRows = (recent || []).slice().reverse();
  const thread = threadRows
    .map((c) => `[${c.role}] ${c.body}`)
    .join("\n");

  const contextLane =
    typeof payload.lane === "string" ? payload.lane : null;
  const ctxQuery = [
    question,
    watch.title,
    watch.summary,
    watch.detail,
    ...actionLines.slice(0, 5),
  ]
    .filter(Boolean)
    .join("\n")
    .slice(0, 1200);
  const ctx = await buildAskContextBundle({
    lane: contextLane,
    title: watch.title,
    summary: watch.summary,
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
    "あなたは Jarvis（秘書 AI）です。状況ウォッチ項目について、ユーザーの質問に日本語で具体的に答えてください。",
    "推測で事実を捏造しない。要対応リストがある場合は日付・店・金額・直し方を明示する。",
    "短く要点から。必要なら次の一手を1〜3個。",
    knowledgeBlock
      ? "外部根拠（神大家DB／OneDriveやり取り／Drive NotebookLM）がある場合はそれを優先し、無いことは推測しない。"
      : "",
    "",
    `【項目】${watch.title}`,
    `【レベル】${watch.level}`,
    `【要約】${watch.summary || "—"}`,
    `【詳細】\n${watch.detail || "—"}`,
    actionLines.length
      ? `【要対応リスト】\n${actionLines.map((l) => `- ${l}`).join("\n")}`
      : "【要対応リスト】なし",
    watch.cursor_prompt ? `【参考プロンプト】\n${watch.cursor_prompt}` : "",
    knowledgeBlock,
    `【直近コメント】\n${thread || "（なし）"}`,
    "",
    `【今回の質問】\n${question}`,
  ]
    .filter(Boolean)
    .join("\n");

  const localPrompt = [
    buildLocalHandoffPrompt({
      kind: "watch",
      id: watch.id,
      title: watch.title,
      summary: watch.summary,
      detail: watch.detail,
      bullets: actionLines,
      cursorPrompt: watch.cursor_prompt,
      comments: threadRows.map((c) => ({ role: c.role, body: c.body })),
      lastUserMessage: question,
    }),
    knowledgeBlock,
  ]
    .filter(Boolean)
    .join("\n\n");

  const resolved = await resolveAskReply({ engine, prompt });
  if (!resolved.ok) {
    revalidatePath(path);
    revalidatePath("/");
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

  const { error: jErr } = await supabase.from("watch_comments").insert({
    watch_id: watchId,
    role: "jarvis",
    body: reply,
  });
  if (jErr) return { ok: false, error: jErr.message };

  revalidatePath(path);
  revalidatePath("/");
  const allNotices = [...knowledgeNotices, ...resolved.fallbackNotices];
  const noticeMsg =
    allNotices.length > 0
      ? allNotices.join(" → ")
      : resolved.via === "cloud"
        ? "Jarvis Cloud が返答しました"
        : "Gemini が返答しました";
  return {
    ok: true,
    message: noticeMsg,
    fallbackNotices: allNotices,
    via: resolved.via,
    localPrompt,
  };
}

export async function enqueueWatchCursorAsk(
  watchId: string,
  path = "/situation",
  opts?: { extraNote?: string; question?: string },
): Promise<WatchCommentActionResult> {
  const supabase = await createClient();
  const { data: watch, error: wErr } = await supabase
    .from("watch_status")
    .select("id,title,summary,detail,payload,cursor_prompt")
    .eq("id", watchId)
    .maybeSingle();
  if (wErr) return { ok: false, error: wErr.message };
  if (!watch) return { ok: false, error: "ウォッチ項目が見つかりません" };

  const payload = asPayload(watch.payload);
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
    .from("watch_comments")
    .select("role,body")
    .eq("watch_id", watchId)
    .order("created_at", { ascending: false })
    .limit(12);
  const comments = (recent || []).slice().reverse();
  const question =
    (opts?.question || "").trim() ||
    [...comments].reverse().find((c) => c.role === "user")?.body ||
    "";

  const actions = Array.isArray(payload.actions) ? payload.actions : [];
  const actionLines = actions
    .slice(0, 20)
    .map((a) => {
      if (!a || typeof a !== "object") return "";
      const row = a as Record<string, unknown>;
      return String(row.line || `${row.date} / ${row.shop} / ¥${row.amount}`);
    })
    .filter(Boolean);

  const prompt = buildLocalHandoffPrompt({
    kind: "watch",
    id: watch.id,
    title: watch.title,
    summary: watch.summary,
    detail: watch.detail,
    bullets: actionLines,
    cursorPrompt: watch.cursor_prompt,
    comments,
    lastUserMessage: question,
    extraNote: opts?.extraNote,
  });

  const cursorAsk: CursorAskState = {
    status: "queued",
    prompt,
    question,
    requested_at: new Date().toISOString(),
    via: "local_worker",
  };
  const { error } = await supabase
    .from("watch_status")
    .update({
      payload: { ...payload, cursor_ask: cursorAsk },
      updated_at: new Date().toISOString(),
    })
    .eq("id", watchId);
  if (error) return { ok: false, error: error.message };

  revalidatePath(path);
  revalidatePath("/");
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

export async function getWatchCursorAskStatus(
  watchId: string,
): Promise<WatchCommentActionResult & { ask?: CursorAskState | null }> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("watch_status")
    .select("payload")
    .eq("id", watchId)
    .maybeSingle();
  if (error) return { ok: false, error: error.message };
  const payload = asPayload(data?.payload);
  const ask =
    payload.cursor_ask && typeof payload.cursor_ask === "object"
      ? (payload.cursor_ask as CursorAskState)
      : null;
  return { ok: true, ask };
}
