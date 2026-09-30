import { createHmac, timingSafeEqual } from "crypto";
import { NextResponse, type NextRequest } from "next/server";
import { createServiceClient } from "@/lib/supabase/admin";

export const runtime = "nodejs";

/**
 * POST /api/line/webhook
 * LINE Messaging API（LINE公式アカウント）の Webhook URL。
 *
 * 検証: X-Line-Signature = base64(HMAC-SHA256(channel_secret, rawBody))
 * 秘密: LINE_OA_CHANNEL_SECRET（LINE Developers のチャネルシークレット）
 *
 * 目的: グループ LINE の本文を OA Bot 経由で平文取得する（受信専用・push 0通）。
 *       line_oa_events に貯め、Mac 側 pull が processed_at を立てて 5.やり取り.md へ流す。
 *
 * 本番URL例:
 *   https://jarvis-dashboard-amber.vercel.app/api/line/webhook
 */
type LineEvent = {
  type?: string;
  webhookEventId?: string;
  replyToken?: string;
  timestamp?: number;
  source?: { type?: string; groupId?: string; roomId?: string; userId?: string };
  message?: { id?: string; type?: string; text?: string };
  [key: string]: unknown;
};

export async function POST(request: NextRequest) {
  const secret = (process.env.LINE_OA_CHANNEL_SECRET || "").trim();
  if (!secret) {
    return NextResponse.json(
      { ok: false, error: "LINE_OA_CHANNEL_SECRET 未設定" },
      { status: 503 },
    );
  }

  const raw = await request.text();
  const signature = (request.headers.get("x-line-signature") || "").trim();
  if (!signature) {
    return NextResponse.json({ ok: false, error: "missing signature" }, { status: 401 });
  }

  const expected = createHmac("sha256", secret).update(raw, "utf8").digest("base64");
  try {
    const a = Buffer.from(signature);
    const b = Buffer.from(expected);
    if (a.length !== b.length || !timingSafeEqual(a, b)) {
      return NextResponse.json({ ok: false, error: "bad signature" }, { status: 401 });
    }
  } catch {
    return NextResponse.json({ ok: false, error: "bad signature" }, { status: 401 });
  }

  let payload: { destination?: string; events?: LineEvent[] };
  try {
    payload = JSON.parse(raw) as { destination?: string; events?: LineEvent[] };
  } catch {
    return NextResponse.json({ ok: false, error: "invalid json" }, { status: 400 });
  }

  const events = Array.isArray(payload.events) ? payload.events : [];
  if (events.length === 0) {
    // 検証リクエスト等（events 空）は 200 を返す
    return NextResponse.json({ ok: true, stored: 0 }, { status: 200 });
  }

  const sb = createServiceClient();
  if (!sb) {
    return NextResponse.json(
      { ok: false, error: "Service Role 未設定" },
      { status: 503 },
    );
  }

  const destination = payload.destination ? String(payload.destination) : null;
  const rows = events.map((ev) => ({
    webhook_event_id: ev.webhookEventId ? String(ev.webhookEventId) : null,
    destination,
    event_type: String(ev.type || "unknown"),
    source_type: ev.source?.type ? String(ev.source.type) : null,
    group_id: ev.source?.groupId ? String(ev.source.groupId) : null,
    room_id: ev.source?.roomId ? String(ev.source.roomId) : null,
    user_id: ev.source?.userId ? String(ev.source.userId) : null,
    message_type: ev.message?.type ? String(ev.message.type) : null,
    message_id: ev.message?.id ? String(ev.message.id) : null,
    text: typeof ev.message?.text === "string" ? ev.message.text : null,
    reply_token: ev.replyToken ? String(ev.replyToken) : null,
    event_timestamp: typeof ev.timestamp === "number" ? ev.timestamp : null,
    raw: ev as Record<string, unknown>,
  }));

  const withId = rows.filter((r) => r.webhook_event_id);
  const withoutId = rows.filter((r) => !r.webhook_event_id);

  try {
    if (withId.length > 0) {
      const { error } = await sb.from("line_oa_events").upsert(withId, {
        onConflict: "webhook_event_id",
        ignoreDuplicates: true,
      });
      if (error) throw error;
    }
    if (withoutId.length > 0) {
      const { error } = await sb.from("line_oa_events").insert(withoutId);
      if (error) throw error;
    }
  } catch (e) {
    console.error("line_oa webhook store", e instanceof Error ? e.message : e);
    // LINE には 200 を返す（再送は冪等キーで吸収）。ただし取りこぼし検知のためログに残す。
    return NextResponse.json({ ok: false, error: "db" }, { status: 500 });
  }

  return NextResponse.json({ ok: true, stored: rows.length }, { status: 200 });
}

/** 疎通確認（ブラウザ／curl） */
export async function GET() {
  const configured = Boolean((process.env.LINE_OA_CHANNEL_SECRET || "").trim());
  return NextResponse.json({
    ok: true,
    service: "line-oa-webhook",
    secret_configured: configured,
  });
}
