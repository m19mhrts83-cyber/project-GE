import { createClient } from "@/lib/supabase/server";
import { applyProgress, type ProgressBody } from "@/lib/reDealStages";
import { NextResponse } from "next/server";

/**
 * 内見〜引渡しの段階・チェックリスト・日付を記録する。
 * 記録のみ（仲介・銀行への送信はしない）。
 */
export async function POST(
  req: Request,
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

  const body = (await req.json().catch(() => ({}))) as ProgressBody;
  if (
    !body ||
    (body.kind !== "viewing" &&
      body.kind !== "acquisition" &&
      body.kind !== "start_acquisition")
  ) {
    return NextResponse.json(
      { error: "kind must be viewing | acquisition | start_acquisition" },
      { status: 400 }
    );
  }

  const { data: row, error: getErr } = await supabase
    .from("kurashift_re_deals")
    .select("id, status, summary_json")
    .eq("id", id)
    .maybeSingle();
  if (getErr || !row) {
    return NextResponse.json(
      { error: getErr?.message || "not found" },
      { status: 404 }
    );
  }

  const now = new Date().toISOString();
  const prevStatus = String(row.status || "info");
  const result = applyProgress(
    {
      status: prevStatus,
      summary_json:
        row.summary_json && typeof row.summary_json === "object"
          ? (row.summary_json as Record<string, unknown>)
          : {},
    },
    body,
    now
  );
  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: 400 });
  }

  const { data: updated, error: upErr } = await supabase
    .from("kurashift_re_deals")
    .update({
      status: result.status,
      summary_json: result.summary_json,
      updated_at: now,
    })
    .eq("id", id)
    .select("id, status, summary_json")
    .single();
  if (upErr || !updated) {
    return NextResponse.json(
      { error: upErr?.message || "update failed" },
      { status: 500 }
    );
  }

  // チェックの付け外しだけならイベントは残さない（タイムラインが埋まるため）
  const patch = "patch" in body ? (body.patch as Record<string, unknown>) : {};
  const onlyChecklist =
    body.kind !== "start_acquisition" &&
    Object.keys(patch || {}).every(
      (k) => k === "checklist" || k === "hearing_answers"
    );
  if (!onlyChecklist || prevStatus !== result.status) {
    await supabase.from("kurashift_re_deal_events").insert({
      deal_id: id,
      event_type: prevStatus !== result.status ? "status_change" : "note",
      from_status: prevStatus,
      to_status: result.status,
      actor: "user",
      summary: result.summary,
      payload: { progress: body.kind },
    });
  }

  return NextResponse.json({ ok: true, deal: updated });
}
