/**
 * 地場業者返信 — Slack から送信／編集／返信なし
 * 署名は PROPERTY_GATE_ACTION_TOKEN（物件ゲートと同系）
 */
import { createHmac, timingSafeEqual } from "crypto";
import { NextResponse } from "next/server";
import { sendGmailViaEnv } from "@/lib/gmail/sendFromEnv";
import { createServiceClient } from "@/lib/supabase/admin";
import { VENDOR_JUDGMENT } from "@/lib/vendorJudgment";

export type VendorReplySlackAction = "send" | "skip" | "edit";

const ID_RE = /^re-vendor-[0-9a-f]{8,32}$/i;

export function isVendorReplyTriageId(id: string): boolean {
  return ID_RE.test((id || "").trim());
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
    (process.env.VENDOR_REPLY_ACTION_TOKEN || "").trim() ||
    (process.env.PROPERTY_GATE_ACTION_TOKEN || "").trim()
  );
}

export function vrActionSig(id: string, action: VendorReplySlackAction): string {
  const secret = actionSecret();
  return createHmac("sha256", secret)
    .update(`vr:${id}:${action}`, "utf8")
    .digest("hex")
    .slice(0, 10);
}

export function vrSigOk(
  id: string,
  action: VendorReplySlackAction,
  sig: string | null | undefined,
): boolean {
  const expected = vrActionSig(id, action);
  const got = (sig || "").trim().toLowerCase();
  if (!got || got.length !== expected.length) return false;
  try {
    return timingSafeEqual(Buffer.from(got), Buffer.from(expected));
  } catch {
    return false;
  }
}

export function parseVrAction(
  raw: string | null | undefined,
): VendorReplySlackAction | null {
  const a = (raw || "").trim().toLowerCase();
  if (a === "send" || a === "s") return "send";
  if (a === "skip" || a === "no_reply" || a === "n" || a === "noreply") {
    return "skip";
  }
  if (a === "edit" || a === "e") return "edit";
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

export async function fetchVendorReplyTriage(
  id: string,
): Promise<TriageRow | null> {
  const sb = createServiceClient();
  if (!sb) return null;
  const { data, error } = await sb
    .from("triage_items")
    .select(
      "id,status,subject,draft_text,original_body,from_email,partner,account,gmail_thread_id,gmail_message_id,payload",
    )
    .eq("id", id)
    .maybeSingle();
  if (error || !data) return null;
  const payload = asPayload(data.payload);
  if (!payload.re_vendor_reply) return null;
  return {
    ...data,
    payload,
  } as TriageRow;
}

export function editFormHtml(row: TriageRow, sig: string): string {
  const draft = row.draft_text || "";
  const inbound = (row.original_body || "").slice(0, 4000);
  const partner = row.partner || "業者";
  const subject = row.subject || "(件名なし)";
  return `<!doctype html><html lang="ja"><meta charset="utf-8"/>
<title>業者返信を編集して送信</title>
<body style="font-family:system-ui;padding:1.5rem;max-width:42rem;color:#111">
<h1 style="font-size:1.2rem">編集して送信 — ${esc(String(partner))}</h1>
<p style="color:#4b5563;font-size:0.9rem">件名: ${esc(String(subject))}</p>
<details style="margin:1rem 0"><summary>受け取った本文（抜粋）</summary>
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
<p style="margin-top:1.5rem;color:#6b7280;font-size:0.8rem">送信は estate（登録宛先）へ。対外送信の了承は本リンク操作＝了承とします。</p>
</body></html>`;
}

export type VrApplyResult = {
  ok: boolean;
  message: string;
  status?: string;
};

export async function applyVendorReplySlack(
  id: string,
  action: VendorReplySlackAction,
  opts?: { body?: string; source?: string },
): Promise<VrApplyResult> {
  const row = await fetchVendorReplyTriage(id);
  if (!row) {
    return { ok: false, message: "対象の業者返信が見つかりません" };
  }
  const st = String(row.status || "pending");
  if (st === "sent") {
    return { ok: false, message: "すでに送信済みです" };
  }
  if (action === "skip" && (st === "skipped" || st === "done")) {
    return { ok: true, message: "すでに返信なし／スキップ済みです", status: st };
  }

  const sb = createServiceClient();
  if (!sb) {
    return { ok: false, message: "Service Role 未設定" };
  }
  const payload = asPayload(row.payload);
  const source = opts?.source || "slack_vr";

  if (action === "skip") {
    const meta = VENDOR_JUDGMENT.no_reply;
    payload.vendor_judgment = {
      code: meta.code,
      label: meta.label,
      at: new Date().toISOString(),
      vendor_id: String(payload.vendor_id || ""),
      source,
    };
    payload.slack_vr_action = { action: "skip", at: new Date().toISOString(), source };
    const { error } = await sb
      .from("triage_items")
      .update({
        status: "skipped",
        payload,
        updated_at: new Date().toISOString(),
      })
      .eq("id", id);
    if (error) return { ok: false, message: error.message };
    return {
      ok: true,
      message: `${meta.toast}（${row.partner || id}）`,
      status: "skipped",
    };
  }

  // send
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

  try {
    const sent = await sendGmailViaEnv({
      to,
      subject,
      body,
      threadId: row.gmail_thread_id || null,
      account: row.account || "estate",
    });
    payload.sent_at = new Date().toISOString();
    payload.gmail_sent_id = sent.id;
    payload.gmail_sent_thread_id = sent.threadId || row.gmail_thread_id;
    payload.gmail_sent_from = sent.from;
    payload.gmail_sent_account = sent.account;
    payload.vendor_reply_sent_at = new Date().toISOString();
    payload.sent_to = to;
    payload.slack_vr_action = {
      action: "send",
      at: new Date().toISOString(),
      source,
    };
    delete payload.last_send_error;
    const { error } = await sb
      .from("triage_items")
      .update({
        status: "sent",
        draft_text: body,
        payload,
        updated_at: new Date().toISOString(),
      })
      .eq("id", id);
    if (error) return { ok: false, message: error.message };
    return {
      ok: true,
      message: `送信しました → ${to}（${row.partner || id}）。YAML 反映は Mac vendor_catchup`,
      status: "sent",
    };
  } catch (e) {
    const errMsg = e instanceof Error ? e.message : String(e);
    payload.last_send_error = errMsg;
    payload.last_send_error_at = new Date().toISOString();
    await sb
      .from("triage_items")
      .update({
        payload,
        updated_at: new Date().toISOString(),
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

export function vrActionUrl(
  id: string,
  action: VendorReplySlackAction,
): string {
  const sig = vrActionSig(id, action);
  const base = dashboardBase();
  return `${base}/api/g/vr/${action}/${encodeURIComponent(id)}?s=${sig}`;
}
