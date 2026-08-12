import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

const ALLOWED = new Set([
  "lifeplan_ingest_actuals",
  "lifeplan_revise_budget",
  "lifeplan_update_century",
  "lifeplan_push_zaim",
  "lifeplan_snapshot",
  "tax_build_yayoi_csv",
  "tax_ingest_accountant_mail",
  "tax_export_evidence",
  "portfolio_weekly",
  "theme_preview",
  "theme_propose_from_status",
  "theme_ensure_index_rb",
  "theme_execute_assist",
  "secrets_upsert",
  "secrets_status",
]);

export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));
  const job_type = String(body.job_type || "");
  if (!ALLOWED.has(job_type)) {
    return NextResponse.json({ error: "job_type not allowed" }, { status: 400 });
  }

  const title = String(body.title || job_type);
  const payload =
    body.payload && typeof body.payload === "object" ? body.payload : {};

  const { data, error } = await supabase
    .from("kurashift_jobs")
    .insert({
      job_type,
      title,
      payload,
      status: "queued",
      created_by: user.email ?? user.id,
    })
    .select("id, job_type, status, created_at")
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, job: data });
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
    .from("kurashift_jobs")
    .select("id, job_type, status, title, created_at, finished_at, error_text")
    .order("created_at", { ascending: false })
    .limit(40);
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ jobs: data });
}
