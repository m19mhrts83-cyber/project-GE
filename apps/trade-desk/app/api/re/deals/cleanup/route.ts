import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import {
  buildCleanupCandidates,
  CLEANUP_MAX_PER_BATCH,
  CLEANUP_REASON_LABEL,
  CLEANUP_STALE_DAYS,
  CLEANUP_UNDO_HOURS,
  isCleanupHardExcluded,
  isUndoBatchFresh,
  type CleanupDealFields,
} from "@/lib/reDealCleanup";

const SELECT_COLS =
  "id, title, status, area, price_man, match_score, inquiry_status, source, summary_json, updated_at, created_at";

async function loadInfoDeals(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  supabase: any
): Promise<CleanupDealFields[]> {
  const { data, error } = await supabase
    .from("kurashift_re_deals")
    .select(SELECT_COLS)
    .eq("status", "info")
    .order("match_score", { ascending: true, nullsFirst: true })
    .limit(500);
  if (error) throw new Error(error.message);
  return (data || []) as CleanupDealFields[];
}

export async function GET() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  try {
    const deals = await loadInfoDeals(supabase);
    const candidates = buildCleanupCandidates(deals);
    return NextResponse.json({
      ok: true,
      stale_days: CLEANUP_STALE_DAYS,
      max_per_batch: CLEANUP_MAX_PER_BATCH,
      reason_labels: CLEANUP_REASON_LABEL,
      candidates,
      count: candidates.length,
    });
  } catch (e) {
    return NextResponse.json(
      { error: e instanceof Error ? e.message : "preview failed" },
      { status: 500 }
    );
  }
}

export async function POST(req: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const body = await req.json().catch(() => ({}));
  const action = String(body.action || "");

  if (action === "apply") {
    const rawIds: unknown[] = Array.isArray(body.deal_ids) ? body.deal_ids : [];
    const dealIds: string[] = [
      ...new Set(
        rawIds.filter(
          (x): x is string => typeof x === "string" && x.length > 0
        )
      ),
    ].slice(0, CLEANUP_MAX_PER_BATCH);
    if (dealIds.length === 0) {
      return NextResponse.json({ error: "deal_ids が空です" }, { status: 400 });
    }

    const { data: rows, error: fetchErr } = await supabase
      .from("kurashift_re_deals")
      .select(SELECT_COLS)
      .in("id", dealIds);
    if (fetchErr) {
      return NextResponse.json({ error: fetchErr.message }, { status: 500 });
    }

    const byId = new Map(
      ((rows || []) as CleanupDealFields[]).map((r) => [r.id, r])
    );
    const now = new Date().toISOString();
    const batchId = crypto.randomUUID();
    const applied: string[] = [];
    const skipped: { id: string; reason: string }[] = [];
    const markReadJobs: string[] = [];

    for (const id of dealIds) {
      const row = byId.get(id);
      if (!row) {
        skipped.push({ id, reason: "not_found" });
        continue;
      }
      if (isCleanupHardExcluded(row)) {
        skipped.push({ id, reason: "hard_excluded" });
        continue;
      }

      const sj =
        row.summary_json && typeof row.summary_json === "object"
          ? { ...(row.summary_json as Record<string, unknown>) }
          : {};
      const prevStatus = String(row.status || "info");
      delete sj.pursue;
      delete sj.pursue_at;
      sj.user_confirmed = false;
      sj.pursue_exclude = true;
      sj.pursue_exclude_at = now;
      sj.bulk_cleanup_batch_id = batchId;
      sj.bulk_cleanup_at = now;
      sj.bulk_cleanup_prev_status = prevStatus;

      const gmailId = typeof sj.gmail_id === "string" ? sj.gmail_id : null;
      const alreadyRead =
        typeof sj.gmail_read_at === "string" && sj.gmail_read_at.length > 0;

      const { error: upErr } = await supabase
        .from("kurashift_re_deals")
        .update({ status: "passed", summary_json: sj, updated_at: now })
        .eq("id", id);
      if (upErr) {
        skipped.push({ id, reason: upErr.message });
        continue;
      }

      await supabase.from("kurashift_re_deal_events").insert({
        deal_id: id,
        event_type: "review_pass",
        from_status: prevStatus,
        to_status: "passed",
        actor: "user",
        summary: "一括整理（見送り）",
        payload: { action: "bulk_cleanup", batch_id: batchId },
      });

      if (gmailId && !alreadyRead) {
        const { data: job } = await supabase
          .from("kurashift_jobs")
          .insert({
            job_type: "re_deal_mark_gmail_read",
            title: `Gmail既読（一括整理）: ${String(row.title || "").slice(0, 60)}`,
            status: "queued",
            payload: {
              deal_id: id,
              action: "pass",
              gmail_id: gmailId,
              source: row.source || sj.account || null,
              batch_id: batchId,
            },
            created_by: user.email ?? user.id,
          })
          .select("id")
          .single();
        if (job?.id) markReadJobs.push(job.id);
      }

      applied.push(id);
    }

    return NextResponse.json({
      ok: true,
      batch_id: batchId,
      applied_count: applied.length,
      applied,
      skipped,
      mark_read_job_count: markReadJobs.length,
      undo_hours: CLEANUP_UNDO_HOURS,
    });
  }

  if (action === "undo") {
    const batchId = typeof body.batch_id === "string" ? body.batch_id : "";
    if (!batchId) {
      return NextResponse.json({ error: "batch_id が必要です" }, { status: 400 });
    }

    const { data: rows, error: fetchErr } = await supabase
      .from("kurashift_re_deals")
      .select(SELECT_COLS)
      .eq("status", "passed")
      .contains("summary_json", { bulk_cleanup_batch_id: batchId })
      .limit(CLEANUP_MAX_PER_BATCH + 5);
    if (fetchErr) {
      return NextResponse.json({ error: fetchErr.message }, { status: 500 });
    }

    // contains が効かない環境向けフォールバック
    let list = (rows || []) as CleanupDealFields[];
    if (list.length === 0) {
      const { data: passed } = await supabase
        .from("kurashift_re_deals")
        .select(SELECT_COLS)
        .eq("status", "passed")
        .order("updated_at", { ascending: false })
        .limit(80);
      list = ((passed || []) as CleanupDealFields[]).filter((d) => {
        const sj = d.summary_json as Record<string, unknown> | null;
        return sj && sj.bulk_cleanup_batch_id === batchId;
      });
    }

    const now = new Date().toISOString();
    const restored: string[] = [];
    const skipped: { id: string; reason: string }[] = [];

    for (const row of list.slice(0, CLEANUP_MAX_PER_BATCH)) {
      const sj =
        row.summary_json && typeof row.summary_json === "object"
          ? { ...(row.summary_json as Record<string, unknown>) }
          : {};
      const at =
        typeof sj.bulk_cleanup_at === "string" ? sj.bulk_cleanup_at : null;
      if (!isUndoBatchFresh(at)) {
        skipped.push({ id: row.id, reason: "undo_expired" });
        continue;
      }
      const prev =
        typeof sj.bulk_cleanup_prev_status === "string"
          ? sj.bulk_cleanup_prev_status
          : "info";
      delete sj.bulk_cleanup_batch_id;
      delete sj.bulk_cleanup_at;
      delete sj.bulk_cleanup_prev_status;
      delete sj.pursue_exclude;
      delete sj.pursue_exclude_at;

      const { error: upErr } = await supabase
        .from("kurashift_re_deals")
        .update({ status: prev || "info", summary_json: sj, updated_at: now })
        .eq("id", row.id);
      if (upErr) {
        skipped.push({ id: row.id, reason: upErr.message });
        continue;
      }

      await supabase.from("kurashift_re_deal_events").insert({
        deal_id: row.id,
        event_type: "status_change",
        from_status: "passed",
        to_status: prev || "info",
        actor: "user",
        summary: "一括整理を戻す",
        payload: { action: "bulk_cleanup_undo", batch_id: batchId },
      });
      restored.push(row.id);
    }

    if (restored.length === 0 && skipped.every((s) => s.reason === "undo_expired")) {
      return NextResponse.json(
        {
          error: `戻せる案件がありません（${CLEANUP_UNDO_HOURS}時間以内のみ）`,
          skipped,
        },
        { status: 400 }
      );
    }

    return NextResponse.json({
      ok: true,
      batch_id: batchId,
      restored_count: restored.length,
      restored,
      skipped,
    });
  }

  return NextResponse.json(
    { error: "action must be apply | undo" },
    { status: 400 }
  );
}
