import { createClient } from "@/lib/supabase/server";
import { evaluateInquiryCandidate } from "@/lib/reInquiryCandidate";
import { loadInquiryAutoConfig } from "@/lib/reInquiryAutoConfig";
import { NextResponse } from "next/server";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ id: string }> }
) {
  const { id } = await ctx.params;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const [{ data: deal, error: dealErr }, { data: messages }, { data: events }] =
    await Promise.all([
      supabase
        .from("kurashift_re_deals")
        .select(
          "id, title, status, source, area, structure, price_man, yield_pct, match_score, summary_json, inquiry_status, inquiry_sent_at, updated_at"
        )
        .eq("id", id)
        .maybeSingle(),
      supabase
        .from("kurashift_re_deal_messages")
        .select(
          "id, direction, kind, subject, from_email, to_email, occurred_at, body_text, gmail_id"
        )
        .eq("deal_id", id)
        .order("occurred_at", { ascending: true }),
      supabase
        .from("kurashift_re_deal_events")
        .select(
          "id, event_type, from_status, to_status, actor, summary, payload, occurred_at"
        )
        .eq("deal_id", id)
        .order("occurred_at", { ascending: true }),
    ]);

  if (dealErr || !deal) {
    return NextResponse.json(
      { error: dealErr?.message || "not found" },
      { status: 404 }
    );
  }

  const { data: attachRows, count: attachCount } = await supabase
    .from("kurashift_re_deal_attachments")
    .select("id, filename, mime_type, size_bytes, storage_path, payload, fetched_at", {
      count: "exact",
    })
    .eq("deal_id", id)
    .order("fetched_at", { ascending: false });

  type TimelineItem = {
    kind: "message" | "event";
    occurred_at: string;
    direction?: string;
    event_type?: string;
    subject?: string;
    summary?: string;
    body_text?: string;
    gmail_id?: string | null;
    actor?: string;
  };

  const timeline: TimelineItem[] = [];
  for (const m of messages || []) {
    timeline.push({
      kind: "message",
      occurred_at: m.occurred_at || "",
      direction: m.direction,
      subject: m.subject || "",
      body_text: m.body_text || "",
      gmail_id: m.gmail_id,
    });
  }
  for (const e of events || []) {
    timeline.push({
      kind: "event",
      occurred_at: e.occurred_at || "",
      event_type: e.event_type,
      summary: e.summary || "",
      actor: e.actor,
    });
  }
  timeline.sort(
    (a, b) =>
      new Date(a.occurred_at).getTime() - new Date(b.occurred_at).getTime()
  );

  const inquiryConfig = loadInquiryAutoConfig();
  const inquiry_eval = evaluateInquiryCandidate(deal, inquiryConfig);

  const attachments = (attachRows || []).map((a) => {
    const payload =
      a.payload && typeof a.payload === "object"
        ? (a.payload as Record<string, unknown>)
        : {};
    const openUrl =
      typeof payload.open_url === "string"
        ? payload.open_url
        : typeof payload.drive_web_view_link === "string"
          ? payload.drive_web_view_link
          : typeof payload.evidence_dir === "string"
            ? `file://${payload.evidence_dir}`
            : null;
    return {
      id: a.id,
      filename: a.filename,
      mime_type: a.mime_type,
      size_bytes: a.size_bytes,
      storage_path: a.storage_path,
      open_url: openUrl,
      kind: typeof payload.kind === "string" ? payload.kind : null,
      fetched_at: a.fetched_at,
    };
  });

  return NextResponse.json({
    ok: true,
    deal,
    timeline,
    attach_count: attachCount || 0,
    attachments,
    inquiry_eval,
  });
}
