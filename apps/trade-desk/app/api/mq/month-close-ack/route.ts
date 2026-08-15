import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import { parseMqMonthCloseAck } from "@/lib/mqMonthCloseNotice";

const META_KEY = "mq_month_close";

function parseValue(raw: unknown): Record<string, unknown> {
  if (raw == null) return {};
  if (typeof raw === "object") return raw as Record<string, unknown>;
  if (typeof raw === "string") {
    try {
      const p = JSON.parse(raw);
      return p && typeof p === "object" ? (p as Record<string, unknown>) : {};
    } catch {
      return {};
    }
  }
  return {};
}

export async function GET() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const { data, error } = await supabase
    .from("sync_meta")
    .select("key, value")
    .eq("key", META_KEY)
    .maybeSingle();
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({
    ok: true,
    acked: parseMqMonthCloseAck(parseValue(data?.value)),
  });
}

export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));
  const month = String(body.month || "").trim();
  if (!/^\d{4}-\d{2}$/.test(month)) {
    return NextResponse.json(
      { error: "month must be YYYY-MM" },
      { status: 400 }
    );
  }

  const { data: existing } = await supabase
    .from("sync_meta")
    .select("value")
    .eq("key", META_KEY)
    .maybeSingle();

  const prev = parseValue(existing?.value);
  const ackedPrev = parseMqMonthCloseAck(prev);
  const acked = {
    ...ackedPrev,
    [month]: new Date().toISOString(),
  };
  const value = {
    ...prev,
    acked,
    updated_at: new Date().toISOString(),
  };

  const { error } = await supabase.from("sync_meta").upsert(
    {
      key: META_KEY,
      value: JSON.stringify(value),
      updated_at: new Date().toISOString(),
    },
    { onConflict: "key" }
  );

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, acked });
}
