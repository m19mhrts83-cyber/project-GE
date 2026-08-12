import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

const ALLOWED = new Set([
  "SONYLIFE_LOGIN_URL",
  "SONYLIFE_USERNAME",
  "SONYLIFE_PASSWORD",
  "SONYLIFE_USERNAME_1",
  "SONYLIFE_PASSWORD_1",
  "SONYLIFE_USERNAME_2",
  "SONYLIFE_PASSWORD_2",
  "BLOOMO_LOGIN_URL",
  "BLOOMO_EMAIL",
  "BLOOMO_PASSWORD",
  "PRUDENTIAL_LOGIN_URL",
  "PRUDENTIAL_USERNAME",
  "PRUDENTIAL_PASSWORD",
  "PRUDENTIAL_USERNAME_1",
  "PRUDENTIAL_PASSWORD_1",
  "PRUDENTIAL_USERNAME_2",
  "PRUDENTIAL_PASSWORD_2",
  "PRUDENTIAL_VALUE_JPY",
  "PRUDENTIAL_CHIKAGE_VALUE_JPY",
  "PRUDENTIAL_LOAN_JPY",
  "PRUDENTIAL_CHIKAGE_LOAN_JPY",
  "AKATSUKI_BRANCH_CODE",
  "AKATSUKI_ACCOUNT_NUMBER",
  "AKATSUKI_LOGIN_PASSWORD",
  "SBI_SEC_USER",
  "SBI_SEC_LOGIN_PASSWORD",
  "AXA_MYAXA_ID",
  "AXA_MYAXA_PASSWORD",
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
  const raw =
    body.updates && typeof body.updates === "object" ? body.updates : {};
  const updates: Record<string, string> = {};
  for (const [k, v] of Object.entries(raw)) {
    if (!ALLOWED.has(k)) continue;
    const s = String(v ?? "").trim();
    if (s) updates[k] = s;
  }
  if (Object.keys(updates).length === 0) {
    return NextResponse.json({ error: "更新対象がありません" }, { status: 400 });
  }

  const keys = Object.keys(updates);
  const { data, error } = await supabase
    .from("kurashift_jobs")
    .insert({
      job_type: "secrets_upsert",
      title: `secrets upsert (${keys.length} keys)`,
      status: "queued",
      payload: { updates },
    })
    .select("id, job_type, status, created_at")
    .single();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }

  // レスポンスに値を載せない
  return NextResponse.json({
    ok: true,
    job: data,
    keys,
    note: "Mac worker が .env.jarvis_private に反映後、ジョブ payload を空にします",
  });
}
