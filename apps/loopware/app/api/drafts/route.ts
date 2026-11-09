import { NextResponse } from "next/server";
import { serviceClient } from "@/lib/supabase";
import { CHANNELS } from "@/lib/draftStore";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** 下書きの一覧（開いているもの → 最近終わったもの） */
export async function GET() {
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  const { data, error } = await sb
    .from("draft_reviews")
    .select("id,case_name,recipient,channel,status,versions,updated_at")
    .neq("status", "dropped")
    .order("updated_at", { ascending: false })
    .limit(40);
  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  const items = (data || []).map((r) => ({
    id: r.id,
    caseName: r.case_name,
    recipient: r.recipient,
    channel: r.channel,
    status: r.status,
    updatedAt: r.updated_at,
    versions: Array.isArray(r.versions) ? r.versions.length : 0,
  }));
  return NextResponse.json({ ok: true, items });
}

/** 画面に貼り付けて新しく始める。body: { caseName, recipient, channel, text, context? } */
export async function POST(req: Request) {
  let b: { caseName?: string; recipient?: string; channel?: string; text?: string; context?: string };
  try {
    b = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 });
  }
  const caseName = String(b.caseName || "").trim().slice(0, 200);
  const recipient = String(b.recipient || "").trim().slice(0, 200);
  const channel = (CHANNELS as readonly string[]).includes(String(b.channel)) ? String(b.channel) : "other";
  const text = String(b.text || "");
  if (!caseName || !recipient || !text.trim()) {
    return NextResponse.json({ ok: false, error: "件名・宛先・本文を入れてください" }, { status: 400 });
  }
  if (text.length > 20000) return NextResponse.json({ ok: false, error: "本文が長すぎます（2万字まで）" }, { status: 413 });
  const sb = serviceClient();
  if (!sb) return NextResponse.json({ ok: false, error: "supabase_unconfigured" }, { status: 503 });
  const versions = [{ label: "v1", text, at: new Date().toISOString(), by: "owner" }];
  const { data, error } = await sb
    .from("draft_reviews")
    .insert({ case_name: caseName, recipient, channel, context: b.context?.slice(0, 6000) || null, versions, source: "loopware" })
    .select("id")
    .single();
  if (error) return NextResponse.json({ ok: false, error: error.message }, { status: 500 });
  return NextResponse.json({ ok: true, id: data.id });
}
