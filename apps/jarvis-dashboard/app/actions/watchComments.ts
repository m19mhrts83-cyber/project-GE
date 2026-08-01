"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";

export type WatchCommentActionResult = {
  ok: boolean;
  error?: string;
  message?: string;
};

async function geminiReply(prompt: string): Promise<{ ok: true; text: string } | { ok: false; error: string }> {
  const key = (process.env.GEMINI_API_KEY || "").trim();
  if (!key) {
    return {
      ok: false,
      error: "GEMINI_API_KEY 未設定。Vercel の環境変数に設定してください。",
    };
  }
  const models = [
    (process.env.GEMINI_MODEL || "").trim(),
    "gemini-flash-latest",
    "gemini-3.6-flash",
    "gemini-flash-lite-latest",
  ].filter((m, i, arr) => m && arr.indexOf(m) === i);

  let lastErr = "";
  for (const model of models) {
    const url =
      `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=` +
      encodeURIComponent(key);
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ role: "user", parts: [{ text: prompt }] }],
      }),
    });
    if (!res.ok) {
      const t = await res.text();
      lastErr = `${model} (${res.status}): ${t.slice(0, 160)}`;
      continue;
    }
    const data = (await res.json()) as {
      candidates?: { content?: { parts?: { text?: string }[] } }[];
    };
    const text =
      data.candidates?.[0]?.content?.parts?.map((p) => p.text || "").join("") ||
      "";
    const out = text.trim();
    if (!out) {
      lastErr = `${model}: 応答が空`;
      continue;
    }
    return { ok: true, text: out };
  }
  return { ok: false, error: `Gemini 失敗: ${lastErr || "利用可能なモデルなし"}` };
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

  const payload =
    watch.payload && typeof watch.payload === "object"
      ? (watch.payload as Record<string, unknown>)
      : {};
  const actions = Array.isArray(payload.actions) ? payload.actions : [];
  const actionLines = actions
    .slice(0, 20)
    .map((a) => {
      if (!a || typeof a !== "object") return "";
      const row = a as Record<string, unknown>;
      return String(row.line || `${row.date} / ${row.shop} / ¥${row.amount} / ${row.proposal || ""}`);
    })
    .filter(Boolean);

  const thread = (recent || [])
    .slice()
    .reverse()
    .map((c) => `[${c.role}] ${c.body}`)
    .join("\n");

  const prompt = [
    "あなたは Jarvis（秘書 AI）です。状況ウォッチ項目について、ユーザーの質問に日本語で具体的に答えてください。",
    "推測で事実を捏造しない。要対応リストがある場合は日付・店・金額・直し方を明示する。",
    "短く要点から。必要なら次の一手を1〜3個。",
    "",
    `【項目】${watch.title}`,
    `【レベル】${watch.level}`,
    `【要約】${watch.summary || "—"}`,
    `【詳細】\n${watch.detail || "—"}`,
    actionLines.length
      ? `【要対応リスト】\n${actionLines.map((l) => `- ${l}`).join("\n")}`
      : "【要対応リスト】なし",
    watch.cursor_prompt ? `【参考プロンプト】\n${watch.cursor_prompt}` : "",
    `【直近コメント】\n${thread || "（なし）"}`,
    "",
    `【今回の質問】\n${question}`,
  ]
    .filter(Boolean)
    .join("\n");

  const reply = await geminiReply(prompt);
  if (!reply.ok) {
    revalidatePath(path);
    return { ok: false, error: reply.error };
  }

  const { error: jErr } = await supabase.from("watch_comments").insert({
    watch_id: watchId,
    role: "jarvis",
    body: reply.text,
  });
  if (jErr) return { ok: false, error: jErr.message };

  revalidatePath(path);
  revalidatePath("/");
  return { ok: true, message: "Jarvis が返答しました" };
}
