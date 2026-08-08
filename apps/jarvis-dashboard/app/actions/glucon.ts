"use server";

import { revalidatePath } from "next/cache";
import { geminiReply } from "@/lib/geminiReply";
import { fetchGluconExamples, fetchGluconLessonRows } from "@/lib/glucon/examples";
import { activityPrompt, resultPrompt } from "@/lib/glucon/prompts";
import {
  lessonsToScheduleRows,
  mergeManualOverride,
  pickActiveCycle,
  reportDeadlineFromGluconDate,
  ymdJst,
} from "@/lib/glucon/schedule";
import type {
  GluconActiveCycle,
  GluconDraftRow,
  GluconExample,
  GluconJournalDay,
  GluconReportKind,
  GluconScheduleRow,
} from "@/lib/glucon/types";
import { createClient } from "@/lib/supabase/server";

function revalidateGlucon() {
  revalidatePath("/glucon");
}

function asExamples(raw: unknown): GluconExample[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((x) => x && typeof x === "object")
    .map((x) => {
      const o = x as Record<string, unknown>;
      return {
        comment_id: String(o.comment_id || ""),
        author_name: String(o.author_name || ""),
        posted_at: o.posted_at ? String(o.posted_at) : null,
        excerpt: String(o.excerpt || ""),
      };
    });
}

function mapDraft(row: Record<string, unknown>): GluconDraftRow {
  return {
    id: String(row.id),
    period_key: String(row.period_key),
    kind: row.kind as GluconReportKind,
    glucon_date: row.glucon_date ? String(row.glucon_date) : null,
    report_deadline: row.report_deadline
      ? String(row.report_deadline)
      : null,
    title: String(row.title || ""),
    body: String(row.body || ""),
    status: row.status as GluconDraftRow["status"],
    examples: asExamples(row.examples),
    journal_day_count: Number(row.journal_day_count || 0),
    post_error: row.post_error ? String(row.post_error) : null,
    posted_at: row.posted_at ? String(row.posted_at) : null,
    westudy_comment_id: row.westudy_comment_id
      ? String(row.westudy_comment_id)
      : null,
    updated_at: row.updated_at ? String(row.updated_at) : undefined,
  };
}

export async function loadGluconSchedules(): Promise<GluconScheduleRow[]> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("glucon_schedule")
    .select("glucon_date, report_deadline, title, source, comment_id")
    .order("glucon_date", { ascending: true });
  return (data || []).map((r) => ({
    glucon_date: String(r.glucon_date),
    report_deadline: String(r.report_deadline),
    title: String(r.title || ""),
    source: (r.source || "scraped") as GluconScheduleRow["source"],
    comment_id: r.comment_id ? String(r.comment_id) : null,
  }));
}

export async function refreshGluconScheduleFromKamiooya(): Promise<{
  ok: boolean;
  error?: string;
  upserted?: number;
  cycle?: GluconActiveCycle | null;
}> {
  const fetched = await fetchGluconLessonRows();
  if (!fetched.ok) return { ok: false, error: fetched.error };

  const parsed = lessonsToScheduleRows(fetched.rows);
  const supabase = await createClient();
  const existing = await loadGluconSchedules();
  const manual = existing.filter((s) => s.source === "manual");

  let upserted = 0;
  for (const row of parsed) {
    const { error } = await supabase.from("glucon_schedule").upsert(
      {
        glucon_date: row.glucon_date,
        report_deadline: row.report_deadline,
        title: row.title,
        source: "scraped",
        comment_id: row.comment_id,
        updated_at: new Date().toISOString(),
      },
      { onConflict: "glucon_date" },
    );
    if (!error) upserted += 1;
  }

  // keep manuals that don't collide with scraped (manual wins on same date if newer — skip overwrite)
  for (const m of manual) {
    const hit = parsed.find((p) => p.glucon_date === m.glucon_date);
    if (hit) continue;
    await supabase.from("glucon_schedule").upsert(
      {
        glucon_date: m.glucon_date,
        report_deadline: m.report_deadline,
        title: m.title,
        source: "manual",
        comment_id: m.comment_id,
        updated_at: new Date().toISOString(),
      },
      { onConflict: "glucon_date" },
    );
  }

  // if no future scraped date, store estimated for UI cache
  let schedules = await loadGluconSchedules();
  const cycle = pickActiveCycle(schedules);
  if (cycle?.estimated) {
    await supabase.from("glucon_schedule").upsert(
      {
        glucon_date: cycle.gluconDate,
        report_deadline: cycle.reportDeadline,
        title: cycle.title,
        source: "estimated",
        updated_at: new Date().toISOString(),
      },
      { onConflict: "glucon_date" },
    );
    schedules = await loadGluconSchedules();
  }

  revalidateGlucon();
  return {
    ok: true,
    upserted,
    cycle: pickActiveCycle(schedules),
  };
}

export async function setManualGluconDate(
  gluconDate: string,
  title = "",
): Promise<{ ok: boolean; error?: string; cycle?: GluconActiveCycle | null }> {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(gluconDate)) {
    return { ok: false, error: "日付は YYYY-MM-DD 形式で入力してください" };
  }
  const supabase = await createClient();
  const deadline = reportDeadlineFromGluconDate(gluconDate);
  const { error } = await supabase.from("glucon_schedule").upsert(
    {
      glucon_date: gluconDate,
      report_deadline: deadline,
      title: title.trim() || `手動: ${gluconDate} グルコン`,
      source: "manual",
      updated_at: new Date().toISOString(),
    },
    { onConflict: "glucon_date" },
  );
  if (error) return { ok: false, error: error.message };
  const schedules = mergeManualOverride(await loadGluconSchedules(), gluconDate, title);
  revalidateGlucon();
  return { ok: true, cycle: pickActiveCycle(schedules) };
}

export async function loadGluconJournalRange(
  from: string,
  to: string,
): Promise<GluconJournalDay[]> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("glucon_journal_days")
    .select("recorded_at, excerpt, keywords, char_count, synced_at")
    .gte("recorded_at", from)
    .lte("recorded_at", to)
    .order("recorded_at", { ascending: true });
  return (data || []).map((r) => ({
    recorded_at: String(r.recorded_at),
    excerpt: String(r.excerpt || ""),
    keywords: Array.isArray(r.keywords) ? (r.keywords as string[]) : [],
    char_count: Number(r.char_count || 0),
    synced_at: r.synced_at ? String(r.synced_at) : undefined,
  }));
}

export async function loadGluconDrafts(
  periodKey: string,
): Promise<GluconDraftRow[]> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("glucon_report_drafts")
    .select("*")
    .eq("period_key", periodKey);
  return (data || []).map((r) => mapDraft(r as Record<string, unknown>));
}

export async function generateGluconDrafts(
  kinds?: GluconReportKind[],
): Promise<{
  ok: boolean;
  error?: string;
  drafts?: GluconDraftRow[];
}> {
  const schedules = await loadGluconSchedules();
  let cycle = pickActiveCycle(schedules);
  if (!cycle) {
    const refreshed = await refreshGluconScheduleFromKamiooya();
    if (!refreshed.ok) return { ok: false, error: refreshed.error };
    cycle = refreshed.cycle || null;
  }
  if (!cycle) {
    return {
      ok: false,
      error: "グルコン日程が未設定です。手動で開催日を入力するか、WeStudy取込後に日程更新してください。",
    };
  }

  const journals = await loadGluconJournalRange(
    cycle.journalFrom,
    cycle.journalTo,
  );
  const targetKinds: GluconReportKind[] = kinds?.length
    ? kinds
    : ["activity", "result"];
  const supabase = await createClient();
  const out: GluconDraftRow[] = [];

  for (const kind of targetKinds) {
    const ex = await fetchGluconExamples(kind);
    const examples = ex.ok ? ex.examples : [];
    const prompt =
      kind === "activity"
        ? activityPrompt({ cycle, journals, examples })
        : resultPrompt({ cycle, journals, examples });
    const res = await geminiReply(prompt);
    if (!res.ok) {
      return { ok: false, error: res.error };
    }
    const body = res.text.trim();
    const title =
      kind === "activity"
        ? `${cycle.periodKey} 活動報告`
        : `${cycle.periodKey} 成果報告`;
    const noResult =
      kind === "result" &&
      (body.includes("該当する成果報告なし") || body.length < 40);

    const { data, error } = await supabase
      .from("glucon_report_drafts")
      .upsert(
        {
          period_key: cycle.periodKey,
          kind,
          glucon_date: cycle.gluconDate,
          report_deadline: cycle.reportDeadline,
          title,
          body,
          status: noResult ? "skipped" : "ready",
          examples,
          journal_day_count: journals.length,
          post_error: null,
          updated_at: new Date().toISOString(),
        },
        { onConflict: "period_key,kind" },
      )
      .select("*")
      .maybeSingle();

    if (error) return { ok: false, error: error.message };
    if (data) out.push(mapDraft(data as Record<string, unknown>));
  }

  revalidateGlucon();
  return { ok: true, drafts: out };
}

export async function saveGluconDraft(
  periodKey: string,
  kind: GluconReportKind,
  body: string,
  title?: string,
): Promise<{ ok: boolean; error?: string; draft?: GluconDraftRow }> {
  const supabase = await createClient();
  const { data: existing } = await supabase
    .from("glucon_report_drafts")
    .select("*")
    .eq("period_key", periodKey)
    .eq("kind", kind)
    .maybeSingle();

  const nextStatus =
    existing?.status === "posted" || existing?.status === "queued"
      ? existing.status
      : "ready";

  const { data, error } = await supabase
    .from("glucon_report_drafts")
    .upsert(
      {
        period_key: periodKey,
        kind,
        title: title?.trim() || existing?.title || `${periodKey} ${kind}`,
        body,
        status: nextStatus === "posted" ? "ready" : nextStatus,
        glucon_date: existing?.glucon_date || null,
        report_deadline: existing?.report_deadline || null,
        examples: existing?.examples || [],
        journal_day_count: existing?.journal_day_count || 0,
        post_error: null,
        updated_at: new Date().toISOString(),
      },
      { onConflict: "period_key,kind" },
    )
    .select("*")
    .maybeSingle();

  if (error) return { ok: false, error: error.message };
  revalidateGlucon();
  return {
    ok: true,
    draft: data ? mapDraft(data as Record<string, unknown>) : undefined,
  };
}

export async function skipGluconDraft(
  periodKey: string,
  kind: GluconReportKind,
): Promise<{ ok: boolean; error?: string }> {
  const supabase = await createClient();
  const { error } = await supabase
    .from("glucon_report_drafts")
    .update({
      status: "skipped",
      updated_at: new Date().toISOString(),
    })
    .eq("period_key", periodKey)
    .eq("kind", kind);
  if (error) return { ok: false, error: error.message };
  revalidateGlucon();
  return { ok: true };
}

export async function queueGluconPost(
  periodKey: string,
  kind: GluconReportKind,
): Promise<{ ok: boolean; error?: string }> {
  const supabase = await createClient();
  const { data: row } = await supabase
    .from("glucon_report_drafts")
    .select("*")
    .eq("period_key", periodKey)
    .eq("kind", kind)
    .maybeSingle();

  if (!row) return { ok: false, error: "下書きがありません" };
  if (!String(row.body || "").trim()) {
    return { ok: false, error: "本文が空です" };
  }
  if (row.status === "posted") {
    return { ok: false, error: "既に投稿済みです。再投稿する場合は本文を保存し直してください。" };
  }
  if (row.status === "queued") {
    return { ok: false, error: "既に投稿待ちです。Mac worker の完了を待ってください。" };
  }
  if (row.status === "skipped") {
    return { ok: false, error: "スキップ済みです。先に本文を保存してください。" };
  }

  const { error } = await supabase
    .from("glucon_report_drafts")
    .update({
      status: "queued",
      post_error: null,
      updated_at: new Date().toISOString(),
    })
    .eq("period_key", periodKey)
    .eq("kind", kind);

  if (error) return { ok: false, error: error.message };
  revalidateGlucon();
  return { ok: true };
}

export async function getGluconPageState(): Promise<{
  today: string;
  cycle: GluconActiveCycle | null;
  schedules: GluconScheduleRow[];
  journals: GluconJournalDay[];
  drafts: GluconDraftRow[];
  journalSyncedAt: string | null;
}> {
  let schedules = await loadGluconSchedules();
  if (!schedules.length) {
    await refreshGluconScheduleFromKamiooya();
    schedules = await loadGluconSchedules();
  }
  const cycle = pickActiveCycle(schedules);
  const journals = cycle
    ? await loadGluconJournalRange(cycle.journalFrom, cycle.journalTo)
    : [];
  const drafts = cycle ? await loadGluconDrafts(cycle.periodKey) : [];
  const supabase = await createClient();
  const { data: lastSync } = await supabase
    .from("glucon_journal_days")
    .select("synced_at")
    .order("synced_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  return {
    today: ymdJst(),
    cycle,
    schedules,
    journals,
    drafts,
    journalSyncedAt: lastSync?.synced_at
      ? String(lastSync.synced_at)
      : null,
  };
}
