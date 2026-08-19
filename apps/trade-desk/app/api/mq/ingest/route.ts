import { createClient } from "@/lib/supabase/server";
import { applyMqYearIngest } from "@/lib/mqIngestDb";
import type { MqAccountMapRow } from "@/lib/mqZaimMap";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));
  const year = Number(body.year) || new Date().getFullYear();
  const force = Boolean(body.force);

  const { data: maps, error: mapErr } = await supabase
    .from("kurashift_mq_account_map")
    .select("*")
    .eq("approved", true)
    .order("priority");
  if (mapErr) {
    return NextResponse.json({ error: mapErr.message }, { status: 500 });
  }

  try {
    const out = await applyMqYearIngest(
      supabase,
      (maps ?? []) as MqAccountMapRow[],
      { year, force, dryRun: false }
    );
    return NextResponse.json({ ok: true, ...out });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : String(e) },
      { status: 500 }
    );
  }
}
