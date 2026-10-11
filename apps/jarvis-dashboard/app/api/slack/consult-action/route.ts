import { createHmac, timingSafeEqual } from "crypto";
import { NextResponse, type NextRequest } from "next/server";
import { createServiceClient } from "@/lib/supabase/admin";

export const runtime = "nodejs";

/**
 * Slack 物件進行ゲート Yes/No
 *
 * GET  ?deal_id=&action=yes|no&token=PROPERTY_GATE_ACTION_TOKEN
 * POST Slack Interactivity（Signing Secret）または JSON {deal_id,action,token}
 *
 * Yes → kurashift_jobs re_deal_inquiry_send（ui_confirmed=true）
 * No  → deal を見送り（passed）
 *
 * 秘密: SLACK_SIGNING_SECRET / PROPERTY_GATE_ACTION_TOKEN（Vercel + jarvis_private）
 */

type GateAction = "yes" | "no";

function htmlPage(title: string, body: string, ok: boolean) {
  const color = ok ? "#065f46" : "#991b1b";
  return new NextResponse(
    `<!doctype html><html lang="ja"><meta charset="utf-8"/>
<title>${title}</title>
<body style="font-family:system-ui;padding:2rem;max-width:36rem;color:${color}">
<h1 style="font-size:1.25rem">${title}</h1>
<pre style="white-space:pre-wrap;background:#f3f4f6;padding:1rem;border-radius:8px;color:#111">${body}</pre>
<p style="color:#6b7280;font-size:0.875rem">このタブは閉じて大丈夫です。結果は Slack #consult にも出ます。</p>
</body></html>`,
    {
      status: ok ? 200 : 400,
      headers: { "Content-Type": "text/html; charset=utf-8" },
    },
  );
}

function verifySlackSignature(
  raw: string,
  timestamp: string,
  signature: string,
  secret: string,
): boolean {
  if (!timestamp || !signature || !secret) return false;
  const ts = Number(timestamp);
  if (!Number.isFinite(ts)) return false;
  // 5分ずれ許容
  if (Math.abs(Date.now() / 1000 - ts) > 60 * 5) return false;
  const base = `v0:${timestamp}:${raw}`;
  const digest =
    "v0=" + createHmac("sha256", secret).update(base, "utf8").digest("hex");
  try {
    const a = Buffer.from(digest);
    const b = Buffer.from(signature);
    return a.length === b.length && timingSafeEqual(a, b);
  } catch {
    return false;
  }
}

function tokenOk(token: string | null | undefined): boolean {
  const expected = (process.env.PROPERTY_GATE_ACTION_TOKEN || "").trim();
  if (!expected) return false;
  const got = (token || "").trim();
  if (!got || got.length !== expected.length) return false;
  try {
    return timingSafeEqual(Buffer.from(got), Buffer.from(expected));
  } catch {
    return false;
  }
}

async function applyGate(
  dealId: string,
  action: GateAction,
  source: string,
): Promise<{ ok: boolean; message: string; job_id?: string }> {
  const sb = createServiceClient();
  if (!sb) {
    return { ok: false, message: "Service Role 未設定" };
  }

  const { data: row, error } = await sb
    .from("kurashift_re_deals")
    .select("id, title, inquiry_status, summary_json, status")
    .eq("id", dealId)
    .maybeSingle();
  if (error || !row) {
    return { ok: false, message: error?.message || "deal not found" };
  }

  const sj =
    row.summary_json && typeof row.summary_json === "object"
      ? ({ ...(row.summary_json as Record<string, unknown>) } as Record<
          string,
          unknown
        >)
      : {};
  const prevGate =
    sj.property_gate && typeof sj.property_gate === "object"
      ? (sj.property_gate as Record<string, unknown>)
      : {};
  const prevDecision = String(prevGate.decision || "");
  const inq = String(row.inquiry_status || sj.inquiry_status || "none");
  const now = new Date().toISOString();
  const title = String(row.title || "").slice(0, 60);

  if (action === "no") {
    if (prevDecision === "no") {
      return { ok: true, message: `既に見送り済: ${title}` };
    }
    sj.inquiry_status = "none";
    sj.property_gate = { ...prevGate, decision: "no", at: now, source };
    sj.auto_pass_reason = sj.auto_pass_reason || "property_gate_no";
    await sb
      .from("kurashift_re_deals")
      .update({
        status: "passed",
        inquiry_status: "none",
        summary_json: sj,
        updated_at: now,
      })
      .eq("id", dealId);
    return { ok: true, message: `見送りにしました: ${title}` };
  }

  // yes
  if (
    prevDecision === "yes" ||
    prevDecision === "sent" ||
    inq === "sending" ||
    inq === "awaiting_reply" ||
    inq === "has_reply"
  ) {
    return {
      ok: true,
      message: `既に進行中/送信済 (inq=${inq}): ${title}`,
    };
  }

  const idempotencyKey = `${dealId}:first_inquiry`;
  const { data: existingJobs } = await sb
    .from("kurashift_jobs")
    .select("id, status, payload")
    .eq("job_type", "re_deal_inquiry_send")
    .in("status", ["queued", "running", "succeeded"])
    .order("created_at", { ascending: false })
    .limit(40);

  const dup = (existingJobs || []).find((j) => {
    const p =
      j.payload && typeof j.payload === "object"
        ? (j.payload as Record<string, unknown>)
        : {};
    return p.deal_id === dealId || p.idempotency_key === idempotencyKey;
  });
  if (dup) {
    return {
      ok: true,
      message: `送信ジョブ既存 (${dup.status}): ${title}`,
      job_id: String(dup.id),
    };
  }

  // handoff 誤ラベル修復
  if (inq === "awaiting_grok" && sj.awaiting_kurashift_first_inquiry) {
    sj.inquiry_status = "awaiting_first_inquiry";
  }

  sj.inquiry_status = "sending";
  sj.property_gate = { ...prevGate, decision: "yes", at: now, source };
  await sb
    .from("kurashift_re_deals")
    .update({
      inquiry_status: "sending",
      summary_json: sj,
      updated_at: now,
    })
    .eq("id", dealId);

  const { data: job, error: jobErr } = await sb
    .from("kurashift_jobs")
    .insert({
      job_type: "re_deal_inquiry_send",
      title: `第一問合せ(Slackゲート): ${title}`,
      status: "queued",
      payload: {
        deal_id: dealId,
        ui_confirmed: true,
        ui_confirmed_at: now,
        slack_gate_yes: true,
        confirm_source: source,
        idempotency_key: idempotencyKey,
      },
      created_by: "slack_consult_action",
    })
    .select("id")
    .single();

  if (jobErr) {
    return { ok: false, message: jobErr.message };
  }
  return {
    ok: true,
    message: `問合せ送信をキューしました: ${title}`,
    job_id: job?.id ? String(job.id) : undefined,
  };
}

function parseAction(raw: string | null | undefined): GateAction | null {
  const a = (raw || "").trim().toLowerCase();
  if (a === "yes" || a === "y" || a === "進めて") return "yes";
  if (a === "no" || a === "n" || a === "見送り") return "no";
  return null;
}

export async function GET(request: NextRequest) {
  const sp = request.nextUrl.searchParams;
  const dealId = (sp.get("deal_id") || "").trim();
  const action = parseAction(sp.get("action"));
  const token = sp.get("token");

  if (!dealId || !action) {
    return htmlPage("エラー", "deal_id と action=yes|no が必要です", false);
  }
  if (!tokenOk(token)) {
    return htmlPage(
      "認証エラー",
      "token が無効です。PROPERTY_GATE_ACTION_TOKEN を確認してください。",
      false,
    );
  }

  const result = await applyGate(dealId, action, "slack_link");
  return htmlPage(
    result.ok ? (action === "yes" ? "Yes 受付" : "No 受付") : "失敗",
    result.message + (result.job_id ? `\njob_id=${result.job_id}` : ""),
    result.ok,
  );
}

export async function POST(request: NextRequest) {
  const contentType = request.headers.get("content-type") || "";
  const raw = await request.text();

  // Slack Interactivity / Events
  const signingSecret = (process.env.SLACK_SIGNING_SECRET || "").trim();
  const slackSig = request.headers.get("x-slack-signature") || "";
  const slackTs = request.headers.get("x-slack-request-timestamp") || "";

  if (slackSig && signingSecret) {
    if (!verifySlackSignature(raw, slackTs, slackSig, signingSecret)) {
      return NextResponse.json({ ok: false, error: "bad slack signature" }, { status: 401 });
    }
  }

  // url_verification (Events API)
  if (contentType.includes("application/json")) {
    try {
      const j = JSON.parse(raw) as Record<string, unknown>;
      if (j.type === "url_verification" && typeof j.challenge === "string") {
        return NextResponse.json({ challenge: j.challenge });
      }
      // JSON API（token）
      if (!slackSig) {
        if (!tokenOk(String(j.token || ""))) {
          return NextResponse.json({ ok: false, error: "bad token" }, { status: 401 });
        }
      }
      // Events: スレ返信 Yes/No
      if (j.type === "event_callback") {
        const ev = (j.event || {}) as Record<string, unknown>;
        if (ev.type === "message" && !ev.bot_id && typeof ev.text === "string") {
          const text = ev.text.trim();
          const action = parseAction(text);
          const thread = String(ev.thread_ts || "");
          // deal_id はスレ親に埋め込まれたものを state から拾えないため、
          // 本文に deal_id=UUID があるときだけ処理
          const m = text.match(
            /([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i,
          );
          if (action && m) {
            const result = await applyGate(m[1], action, "slack_thread");
            return NextResponse.json({ ok: result.ok, ...result, thread });
          }
        }
        return NextResponse.json({ ok: true, ignored: true });
      }

      const dealId = String(j.deal_id || "").trim();
      const action = parseAction(String(j.action || ""));
      if (!dealId || !action) {
        return NextResponse.json(
          { ok: false, error: "deal_id and action required" },
          { status: 400 },
        );
      }
      const result = await applyGate(dealId, action, "json_api");
      return NextResponse.json(result, { status: result.ok ? 200 : 400 });
    } catch {
      return NextResponse.json({ ok: false, error: "invalid json" }, { status: 400 });
    }
  }

  // form-urlencoded: Slack block_actions
  if (contentType.includes("application/x-www-form-urlencoded")) {
    const params = new URLSearchParams(raw);
    const payloadRaw = params.get("payload") || "";
    if (!payloadRaw) {
      return NextResponse.json({ ok: false, error: "missing payload" }, { status: 400 });
    }
    if (!slackSig || !signingSecret) {
      // Interactivity には Signing Secret 必須
      return NextResponse.json(
        { ok: false, error: "SLACK_SIGNING_SECRET required for interactivity" },
        { status: 503 },
      );
    }
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(payloadRaw) as Record<string, unknown>;
    } catch {
      return NextResponse.json({ ok: false, error: "bad payload" }, { status: 400 });
    }
    const actions = Array.isArray(payload.actions) ? payload.actions : [];
    const act = (actions[0] || {}) as Record<string, unknown>;
    const value = String(act.value || "");
    // value: yes:<deal_id> or no:<deal_id>
    const m = value.match(/^(yes|no):([0-9a-f-]{36})$/i);
    if (!m) {
      return NextResponse.json({ ok: false, error: "bad action value" }, { status: 400 });
    }
    const action = parseAction(m[1])!;
    const dealId = m[2];
    const result = await applyGate(dealId, action, "slack_button");
    // Slack は 3 秒以内に ack。本文更新は簡易 text 応答
    return NextResponse.json({
      response_type: "ephemeral",
      text: result.ok
        ? `✅ ${result.message}`
        : `❌ ${result.message}`,
    });
  }

  return NextResponse.json({ ok: false, error: "unsupported content-type" }, { status: 415 });
}

/** 疎通 */
export async function HEAD() {
  return new NextResponse(null, { status: 200 });
}
