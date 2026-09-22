import { createHmac, timingSafeEqual } from "crypto";
import { NextResponse, type NextRequest } from "next/server";
import { createServiceClient } from "@/lib/supabase/admin";

export const runtime = "nodejs";

/**
 * POST /api/todoist/webhook
 * Todoist App Console の Webhook URL。
 * 検証: X-Todoist-Hmac-SHA256 = base64(HMAC-SHA256(client_secret, rawBody))
 * 秘密: TODOIST_APP_CLIENT_SECRET（App Console の client_secret）
 *
 * 本番URL例:
 *   https://jarvis-dashboard-amber.vercel.app/api/todoist/webhook
 */
export async function POST(request: NextRequest) {
  const secret = (process.env.TODOIST_APP_CLIENT_SECRET || "").trim();
  if (!secret) {
    return NextResponse.json(
      { ok: false, error: "TODOIST_APP_CLIENT_SECRET 未設定" },
      { status: 503 },
    );
  }

  const raw = await request.text();
  const hmacHeader = (request.headers.get("x-todoist-hmac-sha256") || "").trim();
  if (!hmacHeader) {
    return NextResponse.json({ ok: false, error: "missing hmac" }, { status: 401 });
  }

  const expected = createHmac("sha256", secret).update(raw, "utf8").digest("base64");
  try {
    const a = Buffer.from(hmacHeader);
    const b = Buffer.from(expected);
    if (a.length !== b.length || !timingSafeEqual(a, b)) {
      return NextResponse.json({ ok: false, error: "bad hmac" }, { status: 401 });
    }
  } catch {
    return NextResponse.json({ ok: false, error: "bad hmac" }, { status: 401 });
  }

  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid json" }, { status: 400 });
  }

  const eventName = String(payload.event_name || "").trim();
  if (!eventName) {
    return NextResponse.json({ ok: false, error: "missing event_name" }, { status: 400 });
  }

  const deliveryId = (request.headers.get("x-todoist-delivery-id") || "").trim() || null;
  const sb = createServiceClient();
  if (!sb) {
    return NextResponse.json(
      { ok: false, error: "Service Role 未設定" },
      { status: 503 },
    );
  }

  const row = {
    delivery_id: deliveryId,
    event_name: eventName,
    user_id: payload.user_id != null ? String(payload.user_id) : null,
    event_data: (payload.event_data as object) || {},
    event_data_extra: (payload.event_data_extra as object) || null,
    initiator: (payload.initiator as object) || null,
  };

  if (deliveryId) {
    const { error } = await sb.from("todoist_webhook_events").upsert(row, {
      onConflict: "delivery_id",
      ignoreDuplicates: true,
    });
    if (error) {
      console.error("todoist_webhook upsert", error.message);
      return NextResponse.json({ ok: false, error: "db" }, { status: 500 });
    }
  } else {
    const { error } = await sb.from("todoist_webhook_events").insert(row);
    if (error) {
      console.error("todoist_webhook insert", error.message);
      return NextResponse.json({ ok: false, error: "db" }, { status: 500 });
    }
  }

  return NextResponse.json({ ok: true }, { status: 200 });
}

/** 疎通確認（ブラウザ／curl） */
export async function GET() {
  const configured = Boolean((process.env.TODOIST_APP_CLIENT_SECRET || "").trim());
  return NextResponse.json({
    ok: true,
    service: "todoist-webhook",
    secret_configured: configured,
  });
}
