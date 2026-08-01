"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import {
  gmailSendConfigured,
  sendGmailViaEnv,
} from "@/lib/gmail/sendFromEnv";
import type { TriageStatus } from "@/lib/triageStatus";

export type TriageActionResult =
  | { ok: true; message?: string }
  | { ok: false; error: string };

function asPayload(raw: unknown): Record<string, unknown> {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    return { ...(raw as Record<string, unknown>) };
  }
  return {};
}

export async function setTriageStatus(
  id: string,
  next: TriageStatus,
  path: string,
): Promise<TriageActionResult> {
  const supabase = await createClient();
  const { error } = await supabase
    .from("triage_items")
    .update({ status: next, updated_at: new Date().toISOString() })
    .eq("id", id);
  if (error) return { ok: false, error: error.message };
  revalidatePath(path);
  revalidatePath("/");
  revalidatePath("/partner");
  return { ok: true };
}

export async function saveTriageDraft(
  id: string,
  draftText: string,
  path: string,
): Promise<TriageActionResult> {
  const supabase = await createClient();
  const { data: row, error: fetchErr } = await supabase
    .from("triage_items")
    .select("payload")
    .eq("id", id)
    .maybeSingle();
  if (fetchErr) return { ok: false, error: fetchErr.message };
  const payload = asPayload(row?.payload);
  payload.web_draft_saved_at = new Date().toISOString();
  const { error } = await supabase
    .from("triage_items")
    .update({
      draft_text: draftText,
      payload,
      updated_at: new Date().toISOString(),
    })
    .eq("id", id);
  if (error) return { ok: false, error: error.message };
  revalidatePath(path);
  revalidatePath("/");
  return { ok: true };
}

export async function reviseTriageDraftWithGemini(
  id: string,
  instruction: string,
  currentDraft: string,
  path: string,
): Promise<TriageActionResult & { draft?: string }> {
  const key = (process.env.GEMINI_API_KEY || "").trim();
  if (!key) {
    return {
      ok: false,
      error:
        "GEMINI_API_KEY 未設定。ローカル Cursor 用に下書きをコピーして見直してください。",
    };
  }
  const prompt = [
    "あなたはビジネス日本語のメール下書き校正アシスタントです。",
    "意味は変えず、指示に従って返信下書きを書き直してください。",
    "出力は本文のみ（挨拶から結びまで）。前置きやコードフェンスは付けない。",
    "",
    "【見直し指示】",
    instruction.trim() || "（丁寧に整えて）",
    "",
    "【現在の下書き】",
    currentDraft,
  ].join("\n");

  // gemini-2.5-flash は新ユーザー向けに 404。night_triage / GHA と同様に latest 系を使う。
  const models = [
    (process.env.GEMINI_MODEL || "").trim(),
    "gemini-flash-latest",
    "gemini-3.6-flash",
    "gemini-flash-lite-latest",
  ].filter((m, i, arr) => m && arr.indexOf(m) === i);

  let lastErr = "";
  try {
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
      const draft = text.trim();
      if (!draft) {
        lastErr = `${model}: 応答が空`;
        continue;
      }

      const save = await saveTriageDraft(id, draft, path);
      if (!save.ok) return save;
      return { ok: true, draft, message: `下書きを更新しました（${model}）` };
    }
    return {
      ok: false,
      error: `Gemini 失敗: ${lastErr || "利用可能なモデルなし"}。ローカル Cursor で見直してください。`,
    };
  } catch (e) {
    return {
      ok: false,
      error: `${e instanceof Error ? e.message : String(e)}。ローカル Cursor で見直してください。`,
    };
  }
}

/**
 * 画面でプレビュー確認したあとの実送信。
 * @param confirmed 必ず true（UI 確認済み）でないと送らない
 */
export async function sendTriageAfterConfirm(
  id: string,
  draftText: string,
  path: string,
  confirmed: boolean,
): Promise<TriageActionResult & { from?: string }> {
  if (confirmed !== true) {
    return { ok: false, error: "送信確認が必要です" };
  }
  const body = draftText.trim();
  if (!body) return { ok: false, error: "下書きが空です" };
  if (!gmailSendConfigured()) {
    return {
      ok: false,
      error:
        "サーバーに Gmail 送信用シークレットがありません。ローカル Cursor / yoritoori_send で送るか、Vercel に GMAIL_*_B64 を設定してください。",
    };
  }

  const supabase = await createClient();
  const { data: it, error: fetchErr } = await supabase
    .from("triage_items")
    .select("*")
    .eq("id", id)
    .maybeSingle();
  if (fetchErr) return { ok: false, error: fetchErr.message };
  if (!it) return { ok: false, error: "対象が見つかりません" };

  const to = String(it.from_email || "").trim();
  if (!to) {
    return {
      ok: false,
      error: "宛先（from_email）が空です。Mac 側で連絡先を確認してください。",
    };
  }
  let subject = String(it.subject || "").trim() || "（件名なし）";
  if (!/^re:/i.test(subject)) subject = `Re: ${subject}`;

  try {
    const sent = await sendGmailViaEnv({
      to,
      subject,
      body,
      threadId: it.gmail_thread_id || null,
    });
    const payload = asPayload(it.payload);
    payload.sent_at = new Date().toISOString();
    payload.gmail_sent_id = sent.id;
    payload.gmail_sent_thread_id = sent.threadId || it.gmail_thread_id;
    payload.yoritoori_appended = false;
    payload.web_draft_saved_at = new Date().toISOString();

    const { error } = await supabase
      .from("triage_items")
      .update({
        status: "sent",
        draft_text: body,
        payload,
        updated_at: new Date().toISOString(),
      })
      .eq("id", id);
    if (error) return { ok: false, error: error.message };

    revalidatePath(path);
    revalidatePath("/");
    revalidatePath("/partner");
    return {
      ok: true,
      from: sent.from,
      message:
        "送信しました。OneDrive のやり取り追記は Mac 同期後に反映されます。",
    };
  } catch (e) {
    return {
      ok: false,
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

export async function gmailSendReady(): Promise<boolean> {
  return gmailSendConfigured();
}
