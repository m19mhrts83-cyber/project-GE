"use server";

import { revalidatePath } from "next/cache";
import { createClient } from "@/lib/supabase/server";
import {
  gmailSendConfigured,
  sendGmailViaEnv,
} from "@/lib/gmail/sendFromEnv";
import { markGmailReadViaEnv } from "@/lib/gmail/markReadFromEnv";
import type { CursorAskState } from "@/lib/localHandoff";
import type { TriageStatus } from "@/lib/triageStatus";

export type TriageActionResult =
  | { ok: true; message?: string }
  | { ok: false; error: string };

/** 確認完了・スキップ時に Gmail を既読にする（snooze / pending 復帰は対象外） */
const MARK_READ_STATUSES: TriageStatus[] = ["skipped", "sent", "done"];

function asPayload(raw: unknown): Record<string, unknown> {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    return { ...(raw as Record<string, unknown>) };
  }
  return {};
}

async function tryMarkTriageGmailRead(row: {
  gmail_message_id?: string | null;
  account?: string | null;
  payload?: Record<string, unknown>;
}): Promise<Record<string, unknown>> {
  const payload = asPayload(row.payload);
  const gid = String(row.gmail_message_id || "").trim();
  if (!gid) return payload;
  if (typeof payload.gmail_read_at === "string" && payload.gmail_read_at) {
    return payload;
  }
  try {
    const r = await markGmailReadViaEnv({
      messageId: gid,
      account: row.account,
    });
    if (r.ok) {
      payload.gmail_read_at = new Date().toISOString();
      delete payload.gmail_read_error;
      delete payload.gmail_read_pending;
    } else {
      payload.gmail_read_pending = true;
      if (r.error || r.skipped) {
        payload.gmail_read_error = String(r.error || r.skipped).slice(0, 200);
      }
    }
  } catch (e) {
    payload.gmail_read_pending = true;
    payload.gmail_read_error = (e instanceof Error ? e.message : String(e)).slice(
      0,
      200,
    );
  }
  return payload;
}

export type SetTriageStatusOpts = {
  /** snoozed 時に payload.snooze_until へ書く ISO */
  snoozeUntil?: string | null;
};

export async function setTriageStatus(
  id: string,
  next: TriageStatus,
  path: string,
  opts?: SetTriageStatusOpts,
): Promise<TriageActionResult & { prevStatus?: TriageStatus }> {
  const supabase = await createClient();
  const { data: row, error: fetchErr } = await supabase
    .from("triage_items")
    .select("status,payload,gmail_message_id,account")
    .eq("id", id)
    .maybeSingle();
  if (fetchErr) return { ok: false, error: fetchErr.message };
  if (!row) return { ok: false, error: "not found" };

  const prevStatus = (row.status || "pending") as TriageStatus;
  let payload = asPayload(row.payload);
  if (next === "snoozed" && opts?.snoozeUntil) {
    payload.snooze_until = opts.snoozeUntil;
  } else if (next === "pending" || next === "skipped" || next === "sent") {
    delete payload.snooze_until;
  }

  if (MARK_READ_STATUSES.includes(next)) {
    payload = await tryMarkTriageGmailRead({
      gmail_message_id: row.gmail_message_id,
      account: row.account,
      payload,
    });
  }

  const { error } = await supabase
    .from("triage_items")
    .update({
      status: next,
      payload,
      updated_at: new Date().toISOString(),
    })
    .eq("id", id);
  if (error) return { ok: false, error: error.message };
  revalidatePath(path);
  revalidatePath("/");
  revalidatePath("/partner");
  revalidatePath("/general");
  revalidatePath("/queue");
  revalidatePath("/archive");
  return { ok: true, prevStatus };
}

/** snooze_until が過ぎた件を pending に戻す（キュー／ホーム用） */
export async function wakeDueSnoozes(): Promise<number> {
  const supabase = await createClient();
  const now = new Date().toISOString();
  const { data, error } = await supabase
    .from("triage_items")
    .select("id,payload")
    .eq("status", "snoozed")
    .limit(80);
  if (error || !data?.length) return 0;
  let n = 0;
  for (const row of data) {
    const pl = asPayload(row.payload);
    const until = typeof pl.snooze_until === "string" ? pl.snooze_until : "";
    if (!until || until > now) continue;
    delete pl.snooze_until;
    const { error: uErr } = await supabase
      .from("triage_items")
      .update({
        status: "pending",
        payload: pl,
        updated_at: new Date().toISOString(),
      })
      .eq("id", row.id);
    if (!uErr) n += 1;
  }
  if (n) {
    revalidatePath("/");
    revalidatePath("/partner");
    revalidatePath("/queue");
  }
  return n;
}

/** パートナー以外（general / openchat 等）の pending を一括スキップ。activity は除外。 */
export async function skipAllNonPartnerPending(
  path: string,
): Promise<TriageActionResult & { count?: number }> {
  const supabase = await createClient();
  const { data: targets, error: fetchErr } = await supabase
    .from("triage_items")
    .select("id,gmail_message_id,account,payload")
    .eq("status", "pending")
    .neq("lane", "partner")
    .neq("kind", "activity");
  if (fetchErr) return { ok: false, error: fetchErr.message };

  const now = new Date().toISOString();
  let count = 0;
  for (const row of targets || []) {
    const payload = await tryMarkTriageGmailRead({
      gmail_message_id: row.gmail_message_id,
      account: row.account,
      payload: asPayload(row.payload),
    });
    const { error } = await supabase
      .from("triage_items")
      .update({ status: "skipped", payload, updated_at: now })
      .eq("id", row.id);
    if (!error) count += 1;
  }

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

/**
 * ジャンル要約の「確認したよ」: kind=skim のみ skipped＋Gmail既読。
 * kind=mail（要確認）は残す。
 */
export async function ackOtherMailDigestSkim(
  path: string,
  itemIds: string[],
  genreId?: string,
): Promise<TriageActionResult & { count?: number }> {
  const ids = [...new Set(itemIds.map((x) => String(x || "").trim()).filter(Boolean))];
  if (!ids.length) {
    return { ok: false, error: "対象がありません" };
  }
  const supabase = await createClient();
  const { data: rows, error: fetchErr } = await supabase
    .from("triage_items")
    .select("id,kind,status,gmail_message_id,account,payload")
    .in("id", ids)
    .eq("status", "pending");
  if (fetchErr) return { ok: false, error: fetchErr.message };

  const now = new Date().toISOString();
  let count = 0;
  for (const row of rows || []) {
    if ((row.kind || "mail") !== "skim") continue;
    const payload = await tryMarkTriageGmailRead({
      gmail_message_id: row.gmail_message_id,
      account: row.account,
      payload: asPayload(row.payload),
    });
    payload.digest_acked_at = now;
    if (genreId) payload.digest_ack_genre = genreId;
    const { error } = await supabase
      .from("triage_items")
      .update({ status: "skipped", payload, updated_at: now })
      .eq("id", row.id);
    if (!error) count += 1;
  }

  revalidatePath(path);
  revalidatePath("/");
  revalidatePath("/general");
  return {
    ok: true,
    count,
    message:
      count > 0
        ? `要約 ${count} 件を確認済み（既読）にしました`
        : "要約用（skim）の未読はありません（要確認は個別に処置してください）",
  };
}

/** ジャンル要約について聞く（カードなし・一時回答） */
export async function askOtherMailDigestGenre(opts: {
  genreLabel: string;
  bullets: string[];
  question: string;
  engine?: "cursor" | "gemini";
}): Promise<TriageActionResult & { answer?: string; via?: string }> {
  const q = (opts.question || "").trim();
  if (!q) return { ok: false, error: "質問が空です" };
  const { resolveAskReply } = await import("@/lib/askEngine");
  const prompt = [
    "あなたは Jarvis（秘書 AI）です。パートナー以外メールのジャンル要約について答えてください。",
    "捏造しない。短く要点から。次の一手があれば1〜3個。",
    "",
    `【ジャンル】${opts.genreLabel}`,
    "【要約メモ】",
    ...(opts.bullets || []).slice(0, 8).map((b) => `- ${b}`),
    "",
    `【質問】${q}`,
  ].join("\n");
  const r = await resolveAskReply({
    engine: opts.engine || "cursor",
    prompt,
  });
  if (!r.ok) {
    return {
      ok: false,
      error: r.error || "聞くに失敗しました",
    };
  }
  return {
    ok: true,
    answer: r.text,
    via: r.via,
    message: r.fallbackNotices?.length
      ? r.fallbackNotices.join(" / ")
      : undefined,
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
    message: `Jarvis Cloud が使えなかったため、Mac のローカル Cursor へ移ります（${args.fallbackReason.slice(0, 80)}）`,
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
        message: "下書きを更新しました（Jarvis Cloud）",
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
    let payload = asPayload(it.payload);
    payload.sent_at = new Date().toISOString();
    payload.gmail_sent_id = sent.id;
    payload.gmail_sent_thread_id = sent.threadId || it.gmail_thread_id;
    payload.yoritoori_appended = false;
    payload.web_draft_saved_at = new Date().toISOString();
    payload.sent_to = to;
    payload.to_source = resolved.source;
    payload = await tryMarkTriageGmailRead({
      gmail_message_id: it.gmail_message_id,
      account: it.account,
      payload,
    });

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

export type MailJaResult = {
  bodyJa?: string;
  subjectJa?: string;
  draftJa?: string;
};

/** 英語本文／下書きがあれば和訳を payload に保存して返す */
export async function ensureMailJa(
  id: string,
  path?: string,
): Promise<TriageActionResult & MailJaResult> {
  const supabase = await createClient();
  const { data: it, error } = await supabase
    .from("triage_items")
    .select("subject,original_body,draft_text,payload")
    .eq("id", id)
    .maybeSingle();
  if (error) return { ok: false, error: error.message };
  if (!it) return { ok: false, error: "not found" };

  const { looksEnglish } = await import("@/lib/mailLanguage");
  const payload = asPayload(it.payload);
  const body = String(it.original_body || "");
  const subject = String(it.subject || "");
  const draft = String(it.draft_text || "");
  let bodyJa = String(payload.body_ja || "");
  let subjectJa = String(payload.subject_ja || "");
  let draftJa = String(payload.draft_ja || "");
  const needBody = looksEnglish(body) && !bodyJa;
  const needSubject = looksEnglish(subject) && !subjectJa;
  const needDraft = looksEnglish(draft) && !draftJa;
  if (!needBody && !needSubject && !needDraft) {
    return { ok: true, bodyJa, subjectJa, draftJa };
  }

  const { geminiReply } = await import("@/lib/geminiReply");
  const r = await geminiReply(
    [
      "次の英語メールを日本語に翻訳してください。意味は変えず、JSONだけ返す。",
      '形式: {"subject_ja":"","body_ja":"","draft_ja":""}',
      "不要なキーは空文字。前置き・コードフェンス禁止。",
      needSubject ? `【件名】\n${subject.slice(0, 300)}` : "",
      needBody ? `【本文】\n${body.slice(0, 6000)}` : "",
      needDraft ? `【下書き】\n${draft.slice(0, 2500)}` : "",
    ]
      .filter(Boolean)
      .join("\n\n"),
  );
  if (!r.ok) {
    return { ok: false, error: r.error, bodyJa, subjectJa, draftJa };
  }
  let parsed: Record<string, string> = {};
  try {
    const raw = r.text.trim().replace(/^```(?:json)?\s*|\s*```$/g, "");
    parsed = JSON.parse(raw) as Record<string, string>;
  } catch {
    if (needBody) parsed.body_ja = r.text.trim();
  }
  if (needSubject) {
    subjectJa = String(parsed.subject_ja || "").trim() || subjectJa;
    if (subjectJa) payload.subject_ja = subjectJa;
  }
  if (needBody) {
    bodyJa = String(parsed.body_ja || "").trim() || r.text.trim();
    if (bodyJa) payload.body_ja = bodyJa;
  }
  if (needDraft) {
    draftJa = String(parsed.draft_ja || "").trim();
    if (draftJa) payload.draft_ja = draftJa;
  }
  payload.body_ja_at = new Date().toISOString();
  const { error: uErr } = await supabase
    .from("triage_items")
    .update({ payload, updated_at: new Date().toISOString() })
    .eq("id", id);
  if (uErr) return { ok: false, error: uErr.message };
  if (path) revalidatePath(path);
  return { ok: true, bodyJa, subjectJa, draftJa };
}

function mailTaskPrompt(opts: {
  id: string;
  subject: string;
  from: string;
  body: string;
  draft: string;
  instruction: string;
}): string {
  return [
    "【ローカル／Cloud Cursor 用】Jarvis ダッシュボードのメールから作業依頼",
    `triage_id: ${opts.id}`,
    `件名: ${opts.subject || "（なし）"}`,
    `From: ${opts.from || "—"}`,
    "",
    "【本文（和訳優先）】",
    opts.body.slice(0, 5000) || "（本文なし）",
    "",
    opts.draft ? `【いまの返信下書き】\n${opts.draft.slice(0, 1500)}` : "",
    "",
    "【ユーザー指示】",
    opts.instruction.trim() || "このメールの指示どおり作業してください。",
    "",
    "返信メールは送らない。リポや手元ファイルで作業してよい。結果は短く日本語で返す。",
  ]
    .filter((x) => x !== "")
    .join("\n");
}

export type MailTaskState = {
  status: "launched" | "error";
  prompt?: string;
  url?: string;
  agent_id?: string;
  run_id?: string;
  requested_at?: string;
  error?: string;
};

export async function launchMailCloudTask(
  id: string,
  instruction: string,
  path: string,
): Promise<
  TriageActionResult & { url?: string; localPrompt?: string }
> {
  const supabase = await createClient();
  const { data: it, error } = await supabase
    .from("triage_items")
    .select("subject,from_email,original_body,draft_text,payload")
    .eq("id", id)
    .maybeSingle();
  if (error) return { ok: false, error: error.message };
  if (!it) return { ok: false, error: "not found" };
  const payload = asPayload(it.payload);
  const body = String(payload.body_ja || it.original_body || "");
  const prompt = mailTaskPrompt({
    id,
    subject: String(payload.subject_ja || it.subject || ""),
    from: String(it.from_email || ""),
    body,
    draft: String(it.draft_text || ""),
    instruction,
  });
  const apiKey = (process.env.CURSOR_API_KEY || "").trim();
  if (!apiKey) {
    return {
      ok: false,
      error: "CURSOR_API_KEY 未設定。Mac ワーカーかローカルコピーを使ってください。",
      localPrompt: prompt,
    };
  }
  const { launchCloudAgentPrompt } = await import("@/lib/cursor/cloudAgent");
  const launched = await launchCloudAgentPrompt({
    apiKey,
    prompt,
    name: "jarvis-mail-task",
    repoUrl: (process.env.CURSOR_CLOUD_REPO_URL || "").trim() || undefined,
    mode: "agent",
  });
  if (!launched.ok) {
    return { ok: false, error: launched.error, localPrompt: prompt };
  }
  payload.mail_task = {
    status: "launched",
    prompt,
    url: launched.url,
    agent_id: launched.agentId,
    run_id: launched.runId,
    requested_at: new Date().toISOString(),
  } satisfies MailTaskState;
  const { error: uErr } = await supabase
    .from("triage_items")
    .update({ payload, updated_at: new Date().toISOString() })
    .eq("id", id);
  if (uErr) return { ok: false, error: uErr.message };
  revalidatePath(path);
  revalidatePath("/");
  return {
    ok: true,
    url: launched.url,
    localPrompt: prompt,
    message: "Cloud Agent を起動しました",
  };
}

export async function enqueueMailCursorAsk(
  id: string,
  instruction: string,
  path: string,
  extraNote?: string,
): Promise<TriageActionResult & { queued?: boolean; localPrompt?: string }> {
  const supabase = await createClient();
  const { data: it, error } = await supabase
    .from("triage_items")
    .select("subject,from_email,original_body,draft_text,payload")
    .eq("id", id)
    .maybeSingle();
  if (error) return { ok: false, error: error.message };
  if (!it) return { ok: false, error: "not found" };
  const payload = asPayload(it.payload);
  const prev = payload.cursor_ask as CursorAskState | undefined;
  if (prev?.status === "queued" || prev?.status === "running") {
    return {
      ok: true,
      queued: true,
      message: "Mac への依頼は処理中です",
    };
  }
  const instr = [instruction.trim(), extraNote?.trim()]
    .filter(Boolean)
    .join("\n");
  const prompt = mailTaskPrompt({
    id,
    subject: String(payload.subject_ja || it.subject || ""),
    from: String(it.from_email || ""),
    body: String(payload.body_ja || it.original_body || ""),
    draft: String(it.draft_text || ""),
    instruction: instr,
  });
  const cursorAsk: CursorAskState = {
    status: "queued",
    prompt,
    question: instr,
    requested_at: new Date().toISOString(),
    via: "local_worker",
  };
  payload.cursor_ask = cursorAsk;
  const { error: uErr } = await supabase
    .from("triage_items")
    .update({ payload, updated_at: new Date().toISOString() })
    .eq("id", id);
  if (uErr) return { ok: false, error: uErr.message };
  revalidatePath(path);
  return {
    ok: true,
    queued: true,
    localPrompt: prompt,
    message: "Mac のローカル Cursor に依頼しました（起動後に返答が付きます）",
  };
}

export async function getMailCursorAskStatus(
  id: string,
): Promise<
  TriageActionResult & {
    ask?: CursorAskState | null;
    mailTask?: MailTaskState | null;
  }
> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("triage_items")
    .select("payload")
    .eq("id", id)
    .maybeSingle();
  if (error) return { ok: false, error: error.message };
  const payload = asPayload(data?.payload);
  const ask =
    payload.cursor_ask && typeof payload.cursor_ask === "object"
      ? (payload.cursor_ask as CursorAskState)
      : null;
  const mailTask =
    payload.mail_task && typeof payload.mail_task === "object"
      ? (payload.mail_task as MailTaskState)
      : null;
  return { ok: true, ask, mailTask };
}
