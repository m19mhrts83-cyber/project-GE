/**
 * メール要対応 — Slack から返信／見送り／Todoist 追加
 * 署名は PROPERTY_GATE_ACTION_TOKEN（物件ゲートと同系）
 */
import { createHmac, timingSafeEqual } from "crypto";
import { NextResponse } from "next/server";
import { sendGmailViaEnv } from "@/lib/gmail/sendFromEnv";
import { createServiceClient } from "@/lib/supabase/admin";
import { createTodoistTask } from "@/lib/todoistTasks";

export type MailActionSlackAction = "reply" | "skip" | "todoist";

const MUTE_META_KEY = "mail_action_skip_mute";
const DEFAULT_MUTE_THRESHOLD = 2;

/** 業者返信 ID は別レーン。それ以外の triage id を対象。 */
export function isMailActionTriageId(id: string): boolean {
  const s = (id || "").trim();
  if (!s || s.length > 80) return false;
  if (/^re-vendor-/i.test(s)) return false;
  return /^[a-zA-Z0-9_.:-]{6,80}$/.test(s);
}

export function htmlPage(title: string, body: string, ok: boolean) {
  const color = ok ? "#065f46" : "#991b1b";
  return new NextResponse(
    `<!doctype html><html lang="ja"><meta charset="utf-8"/>
<title>${esc(title)}</title>
<body style="font-family:system-ui;padding:2rem;max-width:40rem;color:${color}">
<h1 style="font-size:1.25rem">${esc(title)}</h1>
<pre style="white-space:pre-wrap;background:#f3f4f6;padding:1rem;border-radius:8px;color:#111">${esc(body)}</pre>
<p style="color:#6b7280;font-size:0.875rem">このタブは閉じて大丈夫です。</p>
</body></html>`,
    {
      status: ok ? 200 : 400,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "private, no-store",
      },
    },
  );
}

function esc(s: string): string {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function actionSecret(): string {
  return (
    (process.env.MAIL_ACTION_TOKEN || "").trim() ||
    (process.env.PROPERTY_GATE_ACTION_TOKEN || "").trim()
  );
}

export function maActionSig(id: string, action: MailActionSlackAction): string {
  const secret = actionSecret();
  return createHmac("sha256", secret)
    .update(`ma:${id}:${action}`, "utf8")
    .digest("hex")
    .slice(0, 10);
}

export function maSigOk(
  id: string,
  action: MailActionSlackAction,
  sig: string | null | undefined,
): boolean {
  const expected = maActionSig(id, action);
  const got = (sig || "").trim().toLowerCase();
  if (!got || got.length !== expected.length) return false;
  try {
    return timingSafeEqual(Buffer.from(got), Buffer.from(expected));
  } catch {
    return false;
  }
}

export function parseMaAction(
  raw: string | null | undefined,
): MailActionSlackAction | null {
  const a = (raw || "").trim().toLowerCase();
  if (a === "reply" || a === "send" || a === "r") return "reply";
  if (a === "skip" || a === "no" || a === "n" || a === "dismiss") return "skip";
  if (a === "todoist" || a === "task" || a === "t") return "todoist";
  return null;
}

type TriageRow = {
  id: string;
  status: string | null;
  subject: string | null;
  draft_text: string | null;
  original_body: string | null;
  from_email: string | null;
  partner: string | null;
  account: string | null;
  lane: string | null;
  kind: string | null;
  summary: string | null;
  gmail_thread_id: string | null;
  gmail_message_id: string | null;
  payload: Record<string, unknown> | null;
};

function asPayload(raw: unknown): Record<string, unknown> {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    return { ...(raw as Record<string, unknown>) };
  }
  return {};
}

/** GenMail propose と同系のレーン推定 */
export function guessMailTodoistLane(
  subject: string,
  summary: string,
  fromEmail: string,
  partner: string,
): string {
  const blob = `${subject}\n${summary}\n${fromEmail}\n${partner}`;
  const rules: Array<[RegExp, string]> = [
    [/幹事|飲み会|懇親会|新年会|BBQ|遊愛会/i, "kanji"],
    [/家族|珠己|円香|千景|家族会議/i, "kazoku"],
    [/戸建|土地値|楽待|健美家|物件調査|千三つ/i, "kodate"],
    [
      /LEAF|ミニテック|ホームプランナー|修繕|退去|原状|空室|管理会社|Grandole|キャラメル|Tcell/i,
      "properties",
    ],
    [/神大家|WeStudy|グルコン|815|オプチャ/i, "kamiooya"],
    [/Todoist|ダッシュボード|KURASHIFT|アプリ|FRIDAY|GenCode|Mesh/i, "apps"],
    [/Raimo|チャプロ|Cursor|Grok|AI|Jarvis|Genspark|GenMail|課金|カード/i, "ai_raimo"],
  ];
  for (const [pat, lane] of rules) {
    if (pat.test(blob)) return lane;
  }
  return "ai_raimo";
}

export async function fetchMailActionTriage(
  id: string,
): Promise<TriageRow | null> {
  const sb = createServiceClient();
  if (!sb) return null;
  const { data, error } = await sb
    .from("triage_items")
    .select(
      "id,status,subject,draft_text,original_body,from_email,partner,account,lane,kind,summary,gmail_thread_id,gmail_message_id,payload",
    )
    .eq("id", id)
    .maybeSingle();
  if (error || !data) return null;
  const payload = asPayload(data.payload);
  if (payload.re_vendor_reply) return null;
  return { ...data, payload } as TriageRow;
}

export function editFormHtml(row: TriageRow, sig: string): string {
  const draft = row.draft_text || "";
  const inbound = (row.original_body || "").slice(0, 4000);
  const who = row.partner || row.from_email || "相手";
  const subject = row.subject || "(件名なし)";
  return `<!doctype html><html lang="ja"><meta charset="utf-8"/>
<title>メール返信を編集して送信</title>
<body style="font-family:system-ui;padding:1.5rem;max-width:42rem;color:#111">
<h1 style="font-size:1.2rem">返信する — ${esc(String(who))}</h1>
<p style="color:#4b5563;font-size:0.9rem">件名: ${esc(String(subject))}</p>
<details style="margin:1rem 0" open><summary>受け取った本文（抜粋）</summary>
<pre style="white-space:pre-wrap;background:#f9fafb;padding:0.75rem;border-radius:8px;font-size:0.85rem">${esc(inbound)}</pre>
</details>
<form method="POST" action="">
<input type="hidden" name="s" value="${esc(sig)}"/>
<label style="display:block;font-weight:600;margin-bottom:0.35rem">返信草案</label>
<textarea name="body" rows="16" style="width:100%;font:inherit;padding:0.75rem;border:1px solid #d1d5db;border-radius:8px">${esc(draft)}</textarea>
<div style="margin-top:1rem;display:flex;gap:0.75rem;flex-wrap:wrap">
<button type="submit" name="intent" value="send" style="background:#065f46;color:#fff;border:0;padding:0.65rem 1.1rem;border-radius:8px;font-weight:600">この内容で送信</button>
<a href="?s=${encodeURIComponent(sig)}&amp;cancel=1" style="align-self:center;color:#6b7280">キャンセル</a>
</div>
</form>
<p style="margin-top:1.5rem;color:#6b7280;font-size:0.8rem">送信は ${esc(String(row.account || "admin"))} アカウント。本操作＝対外了承とします。</p>
</body></html>`;
}

type MuteEntry = {
  skips: number;
  muted: boolean;
  last_at?: string;
  last_subject?: string;
};

type MuteRegistry = {
  threshold: number;
  entries: Record<string, MuteEntry>;
};

function muteKeyFromEmail(fromEmail: string): string | null {
  const e = (fromEmail || "").trim().toLowerCase();
  if (!e || !e.includes("@")) return null;
  return `from:${e}`;
}

async function loadMuteRegistry(): Promise<MuteRegistry> {
  const sb = createServiceClient();
  const threshold = Number(
    process.env.JARVIS_MAIL_ACTION_MUTE_THRESHOLD || DEFAULT_MUTE_THRESHOLD,
  );
  const base: MuteRegistry = {
    threshold: Number.isFinite(threshold) && threshold > 0 ? threshold : DEFAULT_MUTE_THRESHOLD,
    entries: {},
  };
  if (!sb) return base;
  const { data } = await sb
    .from("sync_meta")
    .select("value")
    .eq("key", MUTE_META_KEY)
    .maybeSingle();
  const raw = data?.value;
  let obj: Record<string, unknown> | null = null;
  if (typeof raw === "string" && raw.trim()) {
    try {
      obj = JSON.parse(raw) as Record<string, unknown>;
    } catch {
      obj = null;
    }
  } else if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    obj = raw as Record<string, unknown>;
  }
  if (!obj) return base;
  const entries =
    obj.entries && typeof obj.entries === "object" && !Array.isArray(obj.entries)
      ? (obj.entries as Record<string, MuteEntry>)
      : {};
  const th = Number(obj.threshold);
  return {
    threshold: Number.isFinite(th) && th > 0 ? th : base.threshold,
    entries,
  };
}

async function saveMuteRegistry(reg: MuteRegistry): Promise<void> {
  const sb = createServiceClient();
  if (!sb) return;
  const now = new Date().toISOString();
  await sb.from("sync_meta").upsert(
    {
      key: MUTE_META_KEY,
      value: JSON.stringify(reg),
      updated_at: now,
    },
    { onConflict: "key" },
  );
}

/** 見送り連続 → 送信者ミュート（Slack 再掲除外）。削除ではなく通知除外。 */
export async function recordMailSkipLearn(
  fromEmail: string,
  subject: string,
): Promise<{ muted: boolean; skips: number; key: string | null }> {
  const key = muteKeyFromEmail(fromEmail);
  if (!key) return { muted: false, skips: 0, key: null };
  const reg = await loadMuteRegistry();
  const prev = reg.entries[key] || { skips: 0, muted: false };
  const skips = (prev.skips || 0) + 1;
  const muted = skips >= reg.threshold || Boolean(prev.muted);
  reg.entries[key] = {
    skips,
    muted,
    last_at: new Date().toISOString(),
    last_subject: (subject || "").slice(0, 120),
  };
  await saveMuteRegistry(reg);
  return { muted, skips, key };
}

export async function isMailSenderMuted(fromEmail: string): Promise<boolean> {
  const key = muteKeyFromEmail(fromEmail);
  if (!key) return false;
  const reg = await loadMuteRegistry();
  return Boolean(reg.entries[key]?.muted);
}

export type MaApplyResult = {
  ok: boolean;
  message: string;
  status?: string;
  todoist_url?: string;
  muted?: boolean;
};

export async function applyMailActionSlack(
  id: string,
  action: MailActionSlackAction,
  opts?: { body?: string; source?: string },
): Promise<MaApplyResult> {
  const row = await fetchMailActionTriage(id);
  if (!row) {
    return { ok: false, message: "対象のメール要対応が見つかりません" };
  }
  const st = String(row.status || "pending");
  if (st === "sent") {
    return { ok: false, message: "すでに送信済みです" };
  }
  if (action === "skip" && (st === "skipped" || st === "done")) {
    return { ok: true, message: "すでに見送り済みです", status: st };
  }
  if (action === "todoist" && st === "todoist") {
    const url = String(asPayload(row.payload).todoist_url || "");
    return {
      ok: true,
      message: url ? `すでに Todoist 登録済: ${url}` : "すでに Todoist 登録済です",
      status: st,
      todoist_url: url || undefined,
    };
  }

  const sb = createServiceClient();
  if (!sb) {
    return { ok: false, message: "Service Role 未設定" };
  }
  const payload = asPayload(row.payload);
  const source = opts?.source || "slack_ma";
  const now = new Date().toISOString();

  if (action === "skip") {
    const learn = await recordMailSkipLearn(
      String(row.from_email || ""),
      String(row.subject || ""),
    );
    payload.slack_ma_action = { action: "skip", at: now, source };
    payload.mail_skip_learn = learn;
    const { error } = await sb
      .from("triage_items")
      .update({
        status: "skipped",
        payload,
        updated_at: now,
      })
      .eq("id", id);
    if (error) return { ok: false, message: error.message };
    const muteNote = learn.muted
      ? ` · 送信者を Slack 通知から除外（見送り ${learn.skips} 回）`
      : learn.key
        ? ` · 見送りカウント ${learn.skips}`
        : "";
    return {
      ok: true,
      message: `見送りにしました（${row.partner || row.from_email || id}）${muteNote}`,
      status: "skipped",
      muted: learn.muted,
    };
  }

  if (action === "todoist") {
    const subject = String(row.subject || "").trim() || "(件名なし)";
    const summaryParts = [
      row.summary || "",
      `From: ${row.from_email || ""}`,
      `lane=${row.lane || ""} kind=${row.kind || ""}`,
      `triage_id=${id}`,
      (row.original_body || "").slice(0, 800),
    ].filter(Boolean);
    const lane = guessMailTodoistLane(
      subject,
      summaryParts.join("\n"),
      String(row.from_email || ""),
      String(row.partner || ""),
    );
    const title = `[メール要対応] ${subject}`.slice(0, 200);
    const created = await createTodoistTask(lane, {
      title,
      summary: summaryParts.join("\n").slice(0, 4000),
    });
    if (!created.ok) {
      return { ok: false, message: `Todoist 起票失敗: ${created.error}` };
    }
    payload.slack_ma_action = { action: "todoist", at: now, source };
    payload.todoist_task_id = created.id;
    payload.todoist_url = created.url;
    payload.todoist_lane = lane;
    const { error } = await sb
      .from("triage_items")
      .update({
        status: "todoist",
        payload,
        updated_at: now,
      })
      .eq("id", id);
    if (error) return { ok: false, message: error.message };
    return {
      ok: true,
      message: `Todoist に登録しました [${lane}]: ${created.url}`,
      status: "todoist",
      todoist_url: created.url,
    };
  }

  // reply（送信）
  const body = (opts?.body ?? row.draft_text ?? "").trim();
  if (!body) {
    return { ok: false, message: "返信本文が空です。編集してから送ってください" };
  }
  const to = String(row.from_email || "").trim();
  if (!to) {
    return { ok: false, message: "宛先（from_email）がありません" };
  }
  let subject = String(row.subject || "").trim() || "（件名なし）";
  if (!/^re:/i.test(subject)) subject = `Re: ${subject}`;
  const account = String(row.account || "admin").trim() || "admin";

  try {
    const sent = await sendGmailViaEnv({
      to,
      subject,
      body,
      threadId: row.gmail_thread_id || null,
      account,
    });
    payload.sent_at = now;
    payload.gmail_sent_id = sent.id;
    payload.gmail_sent_thread_id = sent.threadId || row.gmail_thread_id;
    payload.gmail_sent_from = sent.from;
    payload.gmail_sent_account = sent.account;
    payload.sent_to = to;
    payload.slack_ma_action = { action: "reply", at: now, source };
    delete payload.last_send_error;
    const { error } = await sb
      .from("triage_items")
      .update({
        status: "sent",
        draft_text: body,
        payload,
        updated_at: now,
      })
      .eq("id", id);
    if (error) return { ok: false, message: error.message };
    return {
      ok: true,
      message: `送信しました → ${to}（${row.partner || id}）`,
      status: "sent",
    };
  } catch (e) {
    const errMsg = e instanceof Error ? e.message : String(e);
    payload.last_send_error = errMsg;
    payload.last_send_error_at = now;
    await sb
      .from("triage_items")
      .update({
        payload,
        updated_at: now,
      })
      .eq("id", id);
    return { ok: false, message: errMsg };
  }
}

export function dashboardBase(): string {
  return (
    (process.env.NEXT_PUBLIC_SITE_URL || "").trim().replace(/\/$/, "") ||
    (process.env.JARVIS_DASHBOARD_URL || "").trim().replace(/\/$/, "") ||
    "https://jarvis-dashboard-amber.vercel.app"
  );
}

export function maActionUrl(
  id: string,
  action: MailActionSlackAction,
): string {
  const sig = maActionSig(id, action);
  const base = dashboardBase();
  return `${base}/api/g/ma/${action}/${encodeURIComponent(id)}?s=${sig}`;
}
