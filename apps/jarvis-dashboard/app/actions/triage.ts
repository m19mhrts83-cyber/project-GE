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
  revalidatePath("/general");
  return { ok: true };
}

/** パートナー以外（general / openchat 等）の pending を一括スキップ。activity は除外。 */
export async function skipAllNonPartnerPending(
  path: string,
): Promise<TriageActionResult & { count?: number }> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("triage_items")
    .update({ status: "skipped", updated_at: new Date().toISOString() })
    .eq("status", "pending")
    .neq("lane", "partner")
    .neq("kind", "activity")
    .select("id");
  if (error) return { ok: false, error: error.message };
  const count = data?.length ?? 0;
  revalidatePath(path);
  revalidatePath("/");
  revalidatePath("/general");
  revalidatePath("/partner");
  revalidatePath("/openchat");
  return {
    ok: true,
    count,
    message: count ? `${count} 件をスキップしました` : "スキップ対象の未読はありません",
  };
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

function revisePrompt(instruction: string, currentDraft: string): string {
  return [
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
}

export type ReviseEngine = "gemini" | "cursor";

export type CursorReviseState = {
  status: "queued" | "running" | "done" | "error";
  instruction?: string;
  draft?: string;
  requested_at?: string;
  started_at?: string;
  finished_at?: string;
  error?: string;
  /** cloud = Cloud Agent 成功 / mac_fallback = Mac Worker */
  via?: "cloud" | "mac_fallback";
  fallback_reason?: string;
  cloud_agent_id?: string;
  cloud_run_id?: string;
};

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
        "GEMINI_API_KEY 未設定。Cursor Agent 見直しを選ぶか、ローカル Cursor 用に下書きをコピーしてください。",
    };
  }
  const prompt = revisePrompt(instruction, currentDraft);

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
      error: `Gemini 失敗: ${lastErr || "利用可能なモデルなし"}。Cursor Agent 見直しを試してください。`,
    };
  } catch (e) {
    return {
      ok: false,
      error: `${e instanceof Error ? e.message : String(e)}。Cursor Agent 見直しを試してください。`,
    };
  }
}

async function enqueueMacCursorRevise(args: {
  id: string;
  path: string;
  body: string;
  instr: string;
  payload: Record<string, unknown>;
  fallbackReason: string;
}): Promise<TriageActionResult & { queued?: boolean }> {
  const supabase = await createClient();
  const next = { ...args.payload };
  next.cursor_revise = {
    status: "queued",
    instruction: args.instr,
    draft: args.body,
    requested_at: new Date().toISOString(),
    via: "mac_fallback",
    fallback_reason: args.fallbackReason.slice(0, 300),
  } satisfies CursorReviseState;
  next.web_draft_saved_at = new Date().toISOString();

  const { error } = await supabase
    .from("triage_items")
    .update({
      draft_text: args.body,
      payload: next,
      updated_at: new Date().toISOString(),
    })
    .eq("id", args.id);
  if (error) return { ok: false, error: error.message };

  revalidatePath(args.path);
  revalidatePath("/");
  revalidatePath("/partner");
  return {
    ok: true,
    queued: true,
    message: `Cloud 不可のため Mac ワーカーへキューしました（${args.fallbackReason.slice(0, 80)}）`,
  };
}

/**
 * Cursor Agent 見直し: Cloud 本線 → 失敗時 Mac Worker キュー。
 */
export async function reviseTriageDraftWithCursor(
  id: string,
  instruction: string,
  currentDraft: string,
  path: string,
): Promise<TriageActionResult & { draft?: string; queued?: boolean }> {
  const body = currentDraft.trim();
  if (!body) return { ok: false, error: "下書きが空です" };

  const instr = instruction.trim() || "（丁寧に整えて）";
  const supabase = await createClient();
  const { data: row, error: fetchErr } = await supabase
    .from("triage_items")
    .select("payload")
    .eq("id", id)
    .maybeSingle();
  if (fetchErr) return { ok: false, error: fetchErr.message };

  const payload = asPayload(row?.payload);
  const prev = payload.cursor_revise as CursorReviseState | undefined;
  if (prev?.status === "queued" || prev?.status === "running") {
    return {
      ok: true,
      queued: true,
      message: "Cursor Agent 見直しは処理中です。完了までお待ちください。",
    };
  }

  const apiKey = (process.env.CURSOR_API_KEY || "").trim();
  if (apiKey) {
    const { reviseDraftWithCloudAgent } = await import("@/lib/cursor/cloudRevise");
    const cloud = await reviseDraftWithCloudAgent({
      apiKey,
      instruction: instr,
      draft: body,
      repoUrl: (process.env.CURSOR_CLOUD_REPO_URL || "").trim() || undefined,
      timeoutMs: 75_000,
    });
    if (cloud.ok) {
      const nextPayload = asPayload(payload);
      nextPayload.draft_cursor = cloud.draft;
      nextPayload.web_draft_saved_at = new Date().toISOString();
      nextPayload.cursor_revise = {
        status: "done",
        instruction: instr,
        requested_at: new Date().toISOString(),
        finished_at: new Date().toISOString(),
        via: "cloud",
        cloud_agent_id: cloud.agentId,
        cloud_run_id: cloud.runId,
      } satisfies CursorReviseState;
      const { error } = await supabase
        .from("triage_items")
        .update({
          draft_text: cloud.draft,
          payload: nextPayload,
          updated_at: new Date().toISOString(),
        })
        .eq("id", id);
      if (error) return { ok: false, error: error.message };
      revalidatePath(path);
      revalidatePath("/");
      revalidatePath("/partner");
      return {
        ok: true,
        draft: cloud.draft,
        message: "下書きを更新しました（Cursor Cloud Agent）",
      };
    }
    return enqueueMacCursorRevise({
      id,
      path,
      body,
      instr,
      payload,
      fallbackReason: cloud.error,
    });
  }

  return enqueueMacCursorRevise({
    id,
    path,
    body,
    instr,
    payload,
    fallbackReason: "CURSOR_API_KEY 未設定",
  });
}

export async function reviseTriageDraft(
  id: string,
  instruction: string,
  currentDraft: string,
  path: string,
  engine: ReviseEngine,
): Promise<TriageActionResult & { draft?: string; queued?: boolean }> {
  if (engine === "cursor") {
    return reviseTriageDraftWithCursor(id, instruction, currentDraft, path);
  }
  return reviseTriageDraftWithGemini(id, instruction, currentDraft, path);
}

export async function getCursorReviseStatus(
  id: string,
): Promise<
  TriageActionResult & {
    revise?: CursorReviseState | null;
    draft?: string;
  }
> {
  const supabase = await createClient();
  const { data: row, error } = await supabase
    .from("triage_items")
    .select("payload, draft_text")
    .eq("id", id)
    .maybeSingle();
  if (error) return { ok: false, error: error.message };
  const payload = asPayload(row?.payload);
  const revise =
    payload.cursor_revise && typeof payload.cursor_revise === "object"
      ? (payload.cursor_revise as CursorReviseState)
      : null;
  return {
    ok: true,
    revise,
    draft: String(row?.draft_text || ""),
  };
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
  toOverride?: string,
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

  const { resolvePartnerToEmail } = await import("@/lib/partnerContacts");
  const override = String(toOverride || "").trim();
  const resolved = resolvePartnerToEmail({
    fromEmail: override || it.from_email,
    partner: it.partner,
    folder: it.folder,
    payload: asPayload(it.payload),
  });
  const to = override || resolved.to;
  if (!to) {
    return {
      ok: false,
      error:
        "宛先が未設定です。連絡先一覧にメールが無いか、チャットで宛先を指定してください（従来どおり yoritoori でも可）。",
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
    payload.sent_to = to;
    payload.to_source = resolved.source;

    const { error } = await supabase
      .from("triage_items")
      .update({
        status: "sent",
        draft_text: body,
        from_email: it.from_email || to,
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
