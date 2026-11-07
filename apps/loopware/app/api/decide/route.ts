import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { persistDecision, type DecideBody } from "@/lib/decideStore";

export const runtime = "nodejs";

export async function POST(req: Request) {
  let body: DecideBody;
  try {
    body = (await req.json()) as DecideBody;
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }
  if (!body.decision) {
    return NextResponse.json({ ok: false, error: "no decision" }, { status: 400 });
  }

  const sb = serviceClient();
  if (!sb) {
    // 共有DB未設定。画面は「この端末にだけ保存」と出す
    return NextResponse.json({
      ok: true,
      persisted: false,
      reason: "supabase_unconfigured",
    });
  }

  const res = await persistDecision(sb, body);
  return NextResponse.json(res);
}
