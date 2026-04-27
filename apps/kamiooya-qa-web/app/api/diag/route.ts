import { NextResponse } from "next/server";
import { supabaseAdmin } from "@/lib/supabaseAdmin";

export const runtime = "nodejs";

function mask(s: string) {
  if (!s) return "";
  if (s.length <= 8) return "***";
  return `${s.slice(0, 4)}…${s.slice(-4)}`;
}

export async function GET() {
  const url = process.env.SUPABASE_URL?.trim() || "";
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY?.trim() || "";
  const sessionSecret = process.env.SESSION_SECRET?.trim() || "";

  const urlLooksOk = /^https:\/\/[a-z0-9-]+\.supabase\.co\/?$/.test(url);
  let pingOk = false;
  let pingError: string | null = null;

  try {
    const sb = supabaseAdmin();
    const { error } = await sb.from("users").select("id").limit(1);
    if (error) {
      pingError = error.message || String(error);
    } else {
      pingOk = true;
    }
  } catch (e: any) {
    pingError = e?.message || String(e);
  }

  return NextResponse.json({
    env: {
      SUPABASE_URL: url,
      SUPABASE_URL_looks_valid: urlLooksOk,
      SUPABASE_SERVICE_ROLE_KEY_present: Boolean(key),
      SUPABASE_SERVICE_ROLE_KEY_masked: key ? mask(key) : "",
      SESSION_SECRET_present: Boolean(sessionSecret),
      SESSION_SECRET_masked: sessionSecret ? mask(sessionSecret) : ""
    },
    supabase: {
      users_select_ok: pingOk,
      users_select_error: pingError
    }
  });
}

