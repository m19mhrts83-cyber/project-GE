import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

/** 使い勝手への声の種類（押すだけ）。値は相談メモの metadata.tags に残る */
const TAGS: Record<string, string> = {
  hard_to_see: "見づらい",
  too_many_steps: "手間が多い",
  missing_info: "欲しい情報がない",
  wrong_number: "数字がおかしい",
  good: "ここは良い",
  idea: "こうしたい",
};

/**
 * 画面ごとの「使い勝手への声」。使いながら残し、週次で AI（815 KURASHIFT更新係）が拾って直す。
 * 新しい表は作らず、相談メモ（kurashift_consultations・lane=general）に metadata.kind=app_feedback で残す。
 * POST { path, tags: string[], note? }
 */
export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const body = await req.json().catch(() => ({}));
  const path = String(body.path || "/").slice(0, 200);
  const tags = Array.isArray(body.tags)
    ? Array.from(new Set(body.tags.map((t: unknown) => String(t)).filter((t: string) => t in TAGS))).slice(0, 6)
    : [];
  const note = typeof body.note === "string" ? body.note.trim().slice(0, 1000) : "";
  if (!tags.length && !note) {
    return NextResponse.json({ error: "tags or note required" }, { status: 400 });
  }
  const labels = (tags as string[]).map((t) => TAGS[t]);
  const head = labels.join("・") || note.slice(0, 30);
  const { data, error } = await supabase
    .from("kurashift_consultations")
    .insert({
      title: `【使い勝手】${path}：${head}`.slice(0, 120),
      body: note,
      lane: "general",
      status: "open",
      metadata: {
        kind: "app_feedback",
        path,
        tags,
        tag_labels: labels,
        by: user.email ?? user.id,
        user_agent: (req.headers.get("user-agent") || "").slice(0, 200),
      },
    })
    .select("id")
    .single();
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true, id: data.id });
}
