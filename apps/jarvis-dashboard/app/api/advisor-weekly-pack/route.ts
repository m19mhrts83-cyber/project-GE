import { NextResponse, type NextRequest } from "next/server";
import { buildAdvisorWeeklyPack } from "@/lib/advisorWeeklyPack";

export const runtime = "nodejs";
export const maxDuration = 60;

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let out = 0;
  for (let i = 0; i < a.length; i++) {
    out |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return out === 0;
}

function authorized(request: NextRequest): boolean {
  const expected = (process.env.ADVISOR_WEEKLY_PACK_SECRET || "").trim();
  if (!expected) return false;
  const got = (
    request.headers.get("x-advisor-pack-secret") ||
    request.headers.get("authorization")?.replace(/^Bearer\s+/i, "") ||
    ""
  ).trim();
  return Boolean(got) && timingSafeEqual(got, expected);
}

/**
 * POST/GET /api/advisor-weekly-pack
 * コーチング部長週次から叩く。応答ボディの markdown が本線材料（Macスリープ可）。
 * Auth: Authorization: Bearer $ADVISOR_WEEKLY_PACK_SECRET
 *       または x-advisor-pack-secret
 */
async function handle(request: NextRequest) {
  if ((process.env.JARVIS_ADVISOR_WEEKLY_PACK_DISABLE || "").trim() === "1") {
    return NextResponse.json({ ok: false, error: "disabled" }, { status: 503 });
  }
  if (!authorized(request)) {
    const secretSet = Boolean((process.env.ADVISOR_WEEKLY_PACK_SECRET || "").trim());
    return NextResponse.json(
      {
        ok: false,
        error: secretSet ? "unauthorized" : "ADVISOR_WEEKLY_PACK_SECRET 未設定",
      },
      { status: secretSet ? 401 : 503 },
    );
  }

  const url = new URL(request.url);
  let end = url.searchParams.get("end") || undefined;
  if (request.method === "POST") {
    try {
      const body = (await request.json()) as { end?: string };
      if (body?.end) end = body.end;
    } catch {
      /* empty body ok */
    }
  }

  try {
    const pack = await buildAdvisorWeeklyPack({ end });
    return NextResponse.json({
      ok: true,
      start: pack.start,
      end: pack.end,
      sb_count: pack.sb_count,
      sb_error: pack.sb_error || null,
      markdown: pack.markdown,
    });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: e instanceof Error ? e.message : String(e) },
      { status: 500 },
    );
  }
}

export async function GET(request: NextRequest) {
  return handle(request);
}

export async function POST(request: NextRequest) {
  return handle(request);
}
