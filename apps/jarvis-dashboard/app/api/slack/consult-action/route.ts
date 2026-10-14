import { createHmac, timingSafeEqual } from "crypto";
import { NextResponse, type NextRequest } from "next/server";
import {
  applyGate,
  htmlPage,
  parseAction,
  tokenOk,
} from "@/lib/propertyGateAction";

export const runtime = "nodejs";

/**
 * Slack 物件進行ゲート Yes/No（互換・フル token）
 *
 * GET  ?deal_id=&action=yes|no&token=PROPERTY_GATE_ACTION_TOKEN
 * POST Slack Interactivity（Signing Secret）または JSON {deal_id,action,token}
 *
 * 短縮 URL 本線: /api/g/y|n/{deal_id}?s=…
 */

function verifySlackSignature(
  raw: string,
  timestamp: string,
  signature: string,
  secret: string,
): boolean {
  if (!timestamp || !signature || !secret) return false;
  const ts = Number(timestamp);
  if (!Number.isFinite(ts)) return false;
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

  const signingSecret = (process.env.SLACK_SIGNING_SECRET || "").trim();
  const slackSig = request.headers.get("x-slack-signature") || "";
  const slackTs = request.headers.get("x-slack-request-timestamp") || "";

  if (slackSig && signingSecret) {
    if (!verifySlackSignature(raw, slackTs, slackSig, signingSecret)) {
      return NextResponse.json({ ok: false, error: "bad slack signature" }, { status: 401 });
    }
  }

  if (contentType.includes("application/json")) {
    try {
      const j = JSON.parse(raw) as Record<string, unknown>;
      if (j.type === "url_verification" && typeof j.challenge === "string") {
        return NextResponse.json({ challenge: j.challenge });
      }
      if (!slackSig) {
        if (!tokenOk(String(j.token || ""))) {
          return NextResponse.json({ ok: false, error: "bad token" }, { status: 401 });
        }
      }
      if (j.type === "event_callback") {
        const ev = (j.event || {}) as Record<string, unknown>;
        if (ev.type === "message" && !ev.bot_id && typeof ev.text === "string") {
          const text = ev.text.trim();
          const action = parseAction(text);
          const thread = String(ev.thread_ts || "");
          const m = text.match(
            /([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i,
          );
          if (action && m) {
            const result = await applyGate(m[1], action, "slack_thread");
            return NextResponse.json({ ...result, thread });
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

  if (contentType.includes("application/x-www-form-urlencoded")) {
    const params = new URLSearchParams(raw);
    const payloadRaw = params.get("payload") || "";
    if (!payloadRaw) {
      return NextResponse.json({ ok: false, error: "missing payload" }, { status: 400 });
    }
    if (!slackSig || !signingSecret) {
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
    const m = value.match(/^(yes|no):([0-9a-f-]{36})$/i);
    if (!m) {
      return NextResponse.json({ ok: false, error: "bad action value" }, { status: 400 });
    }
    const action = parseAction(m[1])!;
    const dealId = m[2];
    const result = await applyGate(dealId, action, "slack_button");
    return NextResponse.json({
      response_type: "ephemeral",
      text: result.ok ? `✅ ${result.message}` : `❌ ${result.message}`,
    });
  }

  return NextResponse.json({ ok: false, error: "unsupported content-type" }, { status: 415 });
}

export async function HEAD() {
  return new NextResponse(null, { status: 200 });
}
