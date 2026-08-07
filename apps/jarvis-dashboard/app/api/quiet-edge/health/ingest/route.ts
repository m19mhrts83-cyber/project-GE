import { NextResponse, type NextRequest } from "next/server";
import { createServiceClient } from "@/lib/supabase/admin";

export const runtime = "nodejs";

const ALLOWED_METRICS = new Set([
  "sleep_hours",
  "spo2",
  "respiratory_rate",
  "hrv",
  "resting_hr",
]);

const ALLOWED_SOURCES = new Set(["oramemo", "watch", "health_unknown"]);

const DEFAULT_UNITS: Record<string, string> = {
  sleep_hours: "h",
  spo2: "%",
  respiratory_rate: "breaths/min",
  hrv: "ms",
  resting_hr: "bpm",
};

type MetricIn = {
  metric?: string;
  value?: number | string;
  unit?: string;
  source?: string;
  payload?: Record<string, unknown>;
};

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let out = 0;
  for (let i = 0; i < a.length; i++) {
    out |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return out === 0;
}

function normalizeDate(raw: unknown): string | null {
  if (raw == null) return null;
  const s = String(raw).trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  return null;
}

function asNum(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = typeof v === "number" ? v : Number(String(v).replace(/,/g, ""));
  return Number.isFinite(n) ? n : null;
}

/** POST /api/quiet-edge/health/ingest — iOS Shortcuts → vital_daily */
export async function POST(request: NextRequest) {
  const expected = (process.env.QUIET_EDGE_INGEST_SECRET || "").trim();
  if (!expected) {
    return NextResponse.json(
      { ok: false, error: "QUIET_EDGE_INGEST_SECRET 未設定" },
      { status: 503 },
    );
  }
  const got = (
    request.headers.get("x-quiet-edge-secret") ||
    request.headers.get("authorization")?.replace(/^Bearer\s+/i, "") ||
    ""
  ).trim();
  if (!got || !timingSafeEqual(got, expected)) {
    return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  const sb = createServiceClient();
  if (!sb) {
    return NextResponse.json(
      { ok: false, error: "Service Role 未設定" },
      { status: 503 },
    );
  }

  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid JSON" }, { status: 400 });
  }

  const recorded_at = normalizeDate(body.recorded_at);
  if (!recorded_at) {
    return NextResponse.json(
      { ok: false, error: "recorded_at (YYYY-MM-DD) が必要です" },
      { status: 400 },
    );
  }

  const defaultSource = String(body.source || "health_unknown");
  if (!ALLOWED_SOURCES.has(defaultSource)) {
    return NextResponse.json(
      { ok: false, error: "source は oramemo / watch / health_unknown" },
      { status: 400 },
    );
  }

  const items: MetricIn[] = [];
  if (Array.isArray(body.metrics)) {
    for (const m of body.metrics) {
      if (m && typeof m === "object") items.push(m as MetricIn);
    }
  } else if (body.metric != null) {
    items.push({
      metric: String(body.metric),
      value: body.value as number | string,
      unit: body.unit != null ? String(body.unit) : undefined,
      source: body.source != null ? String(body.source) : defaultSource,
      payload:
        body.payload && typeof body.payload === "object"
          ? (body.payload as Record<string, unknown>)
          : undefined,
    });
  } else {
    // flat map: { sleep_hours: 7.1, spo2: 96, ... }
    for (const key of ALLOWED_METRICS) {
      if (body[key] != null) {
        items.push({
          metric: key,
          value: body[key] as number | string,
          source: defaultSource,
        });
      }
    }
  }

  if (items.length === 0) {
    return NextResponse.json(
      { ok: false, error: "metrics が空です" },
      { status: 400 },
    );
  }

  const now = new Date().toISOString();
  const rows = [];
  for (const it of items) {
    const metric = String(it.metric || "").trim();
    if (!ALLOWED_METRICS.has(metric)) {
      return NextResponse.json(
        {
          ok: false,
          error: `未対応 metric: ${metric}（許可: ${[...ALLOWED_METRICS].join(", ")}）`,
        },
        { status: 400 },
      );
    }
    const value = asNum(it.value);
    if (value == null) {
      return NextResponse.json(
        { ok: false, error: `${metric} の value が不正` },
        { status: 400 },
      );
    }
    const source = String(it.source || defaultSource);
    if (!ALLOWED_SOURCES.has(source)) {
      return NextResponse.json(
        { ok: false, error: `未対応 source: ${source}` },
        { status: 400 },
      );
    }
    rows.push({
      recorded_at,
      metric,
      value,
      unit: it.unit || DEFAULT_UNITS[metric] || null,
      source,
      payload: it.payload || {},
      updated_at: now,
    });
  }

  const { error } = await sb.from("vital_daily").upsert(rows, {
    onConflict: "recorded_at,metric,source",
  });
  if (error) {
    return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  }

  return NextResponse.json({
    ok: true,
    recorded_at,
    upserted: rows.length,
    metrics: rows.map((r) => r.metric),
  });
}
