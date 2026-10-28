/**
 * メール要対応 — Slack から返信／見送り／Todoist 追加
 * 署名は PROPERTY_GATE_ACTION_TOKEN（物件ゲートと同系）
 */
import { createHmac, timingSafeEqual } from "crypto";
import { revalidatePath } from "next/cache";
import { NextResponse } from "next/server";
import { sendGmailViaEnv } from "@/lib/gmail/sendFromEnv";
import {
  recordMailSkipLearn,
  resetMailSkipStreak,
  skipPendingFromMutedSender,
} from "@/lib/mailActionSkipMute";
import { createServiceClient } from "@/lib/supabase/admin";
import { isSelfEmail, parseEmailAddr } from "@/lib/selfEmails";
import { closeTodoistTaskById, createTodoistTask } from "@/lib/todoistTasks";

export type MailActionSlackAction = "reply" | "skip" | "todoist";

export {
  isMailSenderMuted,
  recordMailSkipLearn,
  resetMailSkipStreak,
} from "@/lib/mailActionSkipMute";

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

export type MaApplyResult = {
  ok: boolean;
  message: string;
  status?: string;
  todoist_url?: string;
  muted?: boolean;
  muted_siblings_skipped?: number;
  slack_deleted?: boolean;
  digest_deleted?: boolean;
  digest_updated?: boolean;
  digest_remaining?: number;
};

function revalidateMailActionPaths() {
  try {
    revalidatePath("/");
    revalidatePath("/general");
    revalidatePath("/partner");
    revalidatePath("/queue");
    revalidatePath("/archive");
  } catch {
    /* API route 以外では無視 */
  }
}

/** 見送り後に Slack カードを消す（Bot が投稿したメッセージのみ） */
export async function deleteSlackMaMessage(opts: {
  channel?: string | null;
  ts?: string | null;
}): Promise<boolean> {
  const bot = (process.env.SLACK_BOT_TOKEN || "").trim();
  const channel = String(opts.channel || "").trim();
  const ts = String(opts.ts || "").trim();
  if (!bot || !channel || !ts) return false;
  try {
    const res = await fetch("https://slack.com/api/chat.delete", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${bot}`,
        "Content-Type": "application/json; charset=utf-8",
      },
      body: JSON.stringify({ channel, ts }),
    });
    const j = (await res.json()) as { ok?: boolean; error?: string };
    return Boolean(j.ok);
  } catch {
    return false;
  }
}

async function updateSlackMaMessage(opts: {
  channel: string;
  ts: string;
  text: string;
  blocks: unknown[];
}): Promise<boolean> {
  const bot = (process.env.SLACK_BOT_TOKEN || "").trim();
  if (!bot) return false;
  try {
    const res = await fetch("https://slack.com/api/chat.update", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${bot}`,
        "Content-Type": "application/json; charset=utf-8",
      },
      body: JSON.stringify({
        channel: opts.channel,
        ts: opts.ts,
        text: opts.text,
        blocks: opts.blocks,
      }),
    });
    const j = (await res.json()) as { ok?: boolean; error?: string };
    return Boolean(j.ok);
  } catch {
    return false;
  }
}

type DigestSibling = {
  id: string;
  subject: string | null;
  partner: string | null;
  summary: string | null;
  payload: Record<string, unknown>;
};

function digestScoreOf(pl: Record<string, unknown>): number {
  const d = pl.slack_ma_digest;
  if (d && typeof d === "object" && !Array.isArray(d)) {
    const s = (d as Record<string, unknown>).score;
    if (typeof s === "number") return s;
    if (typeof s === "string" && s.trim()) return Number(s) || 0;
  }
  return 0;
}

function buildDigestUpdatePayload(rows: DigestSibling[]): {
  text: string;
  blocks: unknown[];
} {
  const n = rows.length;
  const when = new Date().toLocaleString("ja-JP", {
    timeZone: "Asia/Tokyo",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  // 本線は短索引のみ（要旨・詳細リンクはスレのカード側）
  const lines = rows.map((row, i) => {
    const partner = String(row.partner || "").trim() || "—";
    let subject = String(row.subject || "(件名なし)").trim();
    if (subject.length > 48) subject = `${subject.slice(0, 47)}…`;
    return `${i + 1}. *${partner}* — ${subject}`;
  });
  const body = lines.join("\n").slice(0, 2900) || "(対象なし)";
  return {
    text: `【メール要対応】残${n}件（${when}）— スレを開いて操作`,
    blocks: [
      {
        type: "header",
        text: {
          type: "plain_text",
          text: `メール要対応 — 残${n}件`,
          emoji: true,
        },
      },
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text:
            `*${when}* · 対応後に更新\n` +
            "👉 *スレッドを開く* → 各カードで返信／見送り／Todoist\n" +
            "本文全文はカード内「詳細を見る」（Dashboard）",
        },
      },
      {
        type: "section",
        text: { type: "mrkdwn", text: body },
      },
      {
        type: "context",
        elements: [
          {
            type: "mrkdwn",
            text: "本線は索引のみ · 見送り／返信／Todoist 後に更新 · 残0で削除",
          },
        ],
      },
    ],
  };
}

/**
 * 同一バッチのダイジェストを同期する。
 * - 残 pending あり → chat.update（一覧を残件だけに）
 * - 残 0 → chat.delete（ダイジェストごと消す）
 */
export async function syncMailActionDigest(opts: {
  digestChannel?: string | null;
  digestTs?: string | null;
}): Promise<{
  deleted?: boolean;
  updated?: boolean;
  remaining?: number;
}> {
  const channel = String(opts.digestChannel || "").trim();
  const ts = String(opts.digestTs || "").trim();
  if (!channel || !ts) return {};

  const sb = createServiceClient();
  if (!sb) return {};

  const { data, error } = await sb
    .from("triage_items")
    .select("id,status,subject,partner,summary,payload")
    .eq("status", "pending")
    .filter("payload->>slack_ma_digest_ts", "eq", ts)
    .limit(20);

  if (error) {
    return {};
  }

  const remaining: DigestSibling[] = (data || [])
    .map((r) => ({
      id: String(r.id),
      subject: r.subject as string | null,
      partner: r.partner as string | null,
      summary: r.summary as string | null,
      payload: asPayload(r.payload),
    }))
    .filter((r) => String(r.payload.slack_ma_digest_ts || "") === ts)
    .sort((a, b) => digestScoreOf(b.payload) - digestScoreOf(a.payload));

  if (remaining.length === 0) {
    const deleted = await deleteSlackMaMessage({ channel, ts });
    return { deleted, remaining: 0 };
  }

  const payload = buildDigestUpdatePayload(remaining);
  const updated = await updateSlackMaMessage({
    channel,
    ts,
    text: payload.text,
    blocks: payload.blocks,
  });
  return { updated, remaining: remaining.length };
}

async function syncDigestFromPayload(
  payload: Record<string, unknown>,
): Promise<{
  digest_deleted?: boolean;
  digest_updated?: boolean;
  digest_remaining?: number;
}> {
  const sync = await syncMailActionDigest({
    digestChannel: String(payload.slack_ma_digest_channel || ""),
    digestTs: String(payload.slack_ma_digest_ts || ""),
  });
  if (sync.remaining === undefined) return {};
  return {
    digest_deleted: sync.deleted,
    digest_updated: sync.updated,
    digest_remaining: sync.remaining,
  };
}

/** 「Todoist追加」で後回しにした返信の目印（朝の再掲で拾い直す） */
export const MAIL_REPLY_WAIT_LABEL = "返信待ち";
/** 後回しの既定期日（JST で 2 日後） */
const MAIL_REPLY_WAIT_DAYS = 2;

function mailReplyWaitDue(): string {
  const jst = new Date(Date.now() + 9 * 3600 * 1000);
  jst.setUTCDate(jst.getUTCDate() + MAIL_REPLY_WAIT_DAYS);
  return jst.toISOString().slice(0, 10);
}

const EMAIL_RE = /^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/;

/** 返信に使える送信元（Vercel の Gmail トークンと対応） */
export const MAIL_SEND_ACCOUNTS = [
  { key: "estate", label: "estate（matsuno.estate@gmail.com）" },
  { key: "admin", label: "admin（admin@livingsupport-matsu.co.jp）" },
  { key: "m19m", label: "m19m（m19m.hrts83@gmail.com）" },
] as const;

export function normalizeMailAccount(raw: string | null | undefined): string {
  const a = String(raw || "").trim().toLowerCase();
  if (a === "livingsupport") return "admin";
  return MAIL_SEND_ACCOUNTS.some((x) => x.key === a) ? a : "";
}

/**
 * 返信の宛先候補。from_email が無い行（パートナーやり取り md 由来）は
 * 本文の最初の他者アドレス（署名・引用ヘッダ）から推定する。
 */
export function guessMailReplyTo(row: {
  from_email?: string | null;
  original_body?: string | null;
}): string {
  const from = parseEmailAddr(row.from_email);
  if (from && !isSelfEmail(from)) return from;
  const found = String(row.original_body || "").match(
    /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g,
  );
  for (const raw of found || []) {
    const addr = raw.toLowerCase();
    if (isSelfEmail(addr) || /no-?reply|mailer-daemon/.test(addr)) continue;
    return addr;
  }
  return "";
}

export async function applyMailActionSlack(
  id: string,
  action: MailActionSlackAction,
  opts?: {
    body?: string;
    source?: string;
    /** 返信の宛先（モーダルで編集）。未指定は from_email → 本文からの推定 */
    to?: string;
    /** 送信元アカウント estate|admin|m19m（モーダルで選択） */
    account?: string;
  },
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
    const pl = asPayload(row.payload);
    const slackDeleted = await deleteSlackMaMessage({
      channel: String(pl.slack_ma_channel || ""),
      ts: String(pl.slack_ma_ts || ""),
    });
    const digestSync = await syncDigestFromPayload(pl);
    return {
      ok: true,
      message: "すでに見送り済みです",
      status: st,
      slack_deleted: slackDeleted,
      ...digestSync,
    };
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
    // 後回し（Todoist）の再掲を見送ったらタスクも閉じる
    if (payload.todoist_task_id && !payload.todoist_closed_at) {
      const closed = await closeTodoistTaskById(
        String(payload.todoist_task_id),
        "【Jarvis】Slack で返信不要（見送り）にしました",
      );
      if (closed.ok) payload.todoist_closed_at = now;
    }
    const { error } = await sb
      .from("triage_items")
      .update({
        status: "skipped",
        payload,
        updated_at: now,
      })
      .eq("id", id);
    if (error) return { ok: false, message: error.message };
    let siblings = 0;
    if (learn.muted) {
      siblings = await skipPendingFromMutedSender({
        fromEmail: String(row.from_email || ""),
        excludeId: id,
        source: "slack_ma_mute",
      });
    }
    const muteNote = learn.muted
      ? ` · 送信者を Slack／Dashboard 未読から除外（見送り ${learn.skips} 回）` +
        (siblings ? ` · 同送信者の未読 ${siblings} 件も閉じました` : "")
      : learn.key
        ? ` · 見送りカウント ${learn.skips}`
        : "";
    // チャット上からカードを消す（振り返り不要）
    const slackDeleted = await deleteSlackMaMessage({
      channel: String(payload.slack_ma_channel || ""),
      ts: String(payload.slack_ma_ts || ""),
    });
    // 同一バッチのダイジェスト: 残 pending で更新／0件なら削除
    const digestSync = await syncDigestFromPayload(payload);
    revalidateMailActionPaths();
    return {
      ok: true,
      message: `見送りにしました（${row.partner || row.from_email || id}）${muteNote}`,
      status: "skipped",
      muted: learn.muted,
      muted_siblings_skipped: siblings || undefined,
      slack_deleted: slackDeleted,
      ...digestSync,
    };
  }

  if (action === "todoist") {
    // 同じメールで起票済みなら作り直さない（ボタン再押下・別カードからの押下）
    if (payload.todoist_task_id && payload.todoist_url) {
      return {
        ok: true,
        message: `Todoist に登録済みです: ${String(payload.todoist_url)}`,
        status: "todoist",
        todoist_url: String(payload.todoist_url),
      };
    }
    const subject = String(row.subject || "").trim() || "(件名なし)";
    const partner = String(row.partner || "").trim();
    const fromEmail = String(row.from_email || "");
    const lane = guessMailTodoistLane(
      subject,
      [row.summary || "", fromEmail, partner].join("\n"),
      fromEmail,
      partner,
    );
    const titleBase = partner
      ? `[メール要対応][${partner}] ${subject}`
      : `[メール要対応] ${subject}`;
    const title = titleBase.slice(0, 200);
    const outLinks = [
      `triage_id=${id}`,
      row.gmail_thread_id ? `gmail_thread=${row.gmail_thread_id}` : "",
      row.gmail_message_id ? `gmail_message=${row.gmail_message_id}` : "",
    ].filter(Boolean);
    const summaryBlock = [
      "【Jarvis】",
      `サマリ: ${(row.summary || subject).replace(/\s+/g, " ").slice(0, 280)}`,
      "アウトプット:",
      ...outLinks.map((l) => `- ${l}`),
      "",
      `From: ${fromEmail}`,
      `lane=${row.lane || ""} kind=${row.kind || ""}`,
      (row.original_body || "").slice(0, 600),
    ].join("\n").slice(0, 4000);
    const created = await createTodoistTask(lane, {
      title,
      summary: summaryBlock,
      labels: ["quick", MAIL_REPLY_WAIT_LABEL],
      // 期日なしだと 313 にも朝の再掲にも乗らず埋もれる
      due: mailReplyWaitDue(),
    });
    if (!created.ok) {
      return { ok: false, message: `Todoist 起票失敗: ${created.error}` };
    }
    await resetMailSkipStreak(fromEmail);
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
    const digestSync = await syncDigestFromPayload(payload);
    revalidateMailActionPaths();
    return {
      ok: true,
      message: `Todoist に登録しました [${lane}]: ${created.url}`,
      status: "todoist",
      todoist_url: created.url,
      ...digestSync,
    };
  }

  // reply（送信）
  const body = (opts?.body ?? row.draft_text ?? "").trim();
  if (!body) {
    return { ok: false, message: "返信本文が空です。編集してから送ってください" };
  }
  const to = (opts?.to || guessMailReplyTo(row)).trim();
  if (!to) {
    return { ok: false, message: "宛先がありません。宛先欄に入力してください" };
  }
  if (!EMAIL_RE.test(to)) {
    return { ok: false, message: `宛先の形式が正しくありません: ${to}` };
  }
  let subject = String(row.subject || "").trim() || "（件名なし）";
  if (!/^re:/i.test(subject)) subject = `Re: ${subject}`;
  const receivedAccount = normalizeMailAccount(row.account);
  const account = normalizeMailAccount(opts?.account) || receivedAccount || "estate";

  try {
    const sent = await sendGmailViaEnv({
      to,
      subject,
      body,
      // threadId は受信したメールボックスのものなので、送信元を変えたら付けない
      threadId: account === receivedAccount ? row.gmail_thread_id || null : null,
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
    // 後回し（Todoist）から返信したらタスクも閉じる
    const todoistTaskId = String(payload.todoist_task_id || "");
    if (todoistTaskId && !payload.todoist_closed_at) {
      const closed = await closeTodoistTaskById(
        todoistTaskId,
        `【Jarvis】Slack から返信送信済み → ${to}`,
      );
      if (closed.ok) {
        payload.todoist_closed_at = now;
        await sb.from("triage_items").update({ payload }).eq("id", id);
      }
    }
    await resetMailSkipStreak(to);
    const digestSync = await syncDigestFromPayload(payload);
    revalidateMailActionPaths();
    return {
      ok: true,
      message: `送信しました → ${to}（${row.partner || id}）`,
      status: "sent",
      ...digestSync,
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
