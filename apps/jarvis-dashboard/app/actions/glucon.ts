"use server";

import { revalidatePath } from "next/cache";
import { geminiReply } from "@/lib/geminiReply";
import { fetchGluconExamples, fetchGluconLessonRows } from "@/lib/glucon/examples";
import {
  queueBlockReason,
  resolveDraftSaveStatus,
} from "@/lib/glucon/postGuard";
import {
  activityPrompt,
  getMemberHeaderStatus,
  resultPrompt,
} from "@/lib/glucon/prompts";
import {
  buildResultScoringHints,
  formatRubricForPrompt,
  loadScoringRules,
  type ResultScoringHints,
} from "@/lib/glucon/scoring";
import {
  lessonsToScheduleRows,
  mergeManualOverride,
  pickActiveCycle,
  reportDeadlineFromGluconDate,
  ymdJst,
} from "@/lib/glucon/schedule";
import { buildGluconMonthlyDigest } from "@/lib/glucon/monthlyDigest";
import type {
  GluconActiveCycle,
  GluconDraftRow,
  GluconExample,
  GluconJournalDay,
  GluconMemberHeaderStatus,
  GluconMonthlyDigestPreview,
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

function mapDraft(
  row: Record<string, unknown>,
  opts?: { includeExamples?: boolean },
): GluconDraftRow {
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
    // UI には不要。RSC / Server Action 応答を軽くするため既定は空
    examples: opts?.includeExamples ? asExamples(row.examples) : [],
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

/** pickActiveCycle がメモリ上で推定した日程を DB に残す（画面・ウォッチと共有） */
async function persistEstimatedCycleIfNeeded(
  cycle: GluconActiveCycle | null,
  schedules: GluconScheduleRow[],
): Promise<GluconScheduleRow[]> {
  if (!cycle?.estimated) return schedules;
  const exists = schedules.some((s) => s.glucon_date === cycle.gluconDate);
  if (exists) {
    const row = schedules.find((s) => s.glucon_date === cycle.gluconDate);
    if (row?.source === "estimated" || row?.source === "manual") return schedules;
    // scraped が未来日なら推定不要
    return schedules;
  }
  const supabase = await createClient();
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
  return loadGluconSchedules();
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
  try {
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
        error:
          "グルコン日程が未設定です。手動で開催日を入力するか、WeStudy取込後に日程更新してください。",
      };
    }

    const journals = await loadGluconJournalRange(
      cycle.journalFrom,
      cycle.journalTo,
    );
    const monthly = await buildGluconMonthlyDigest(
      cycle.journalFrom,
      cycle.journalTo,
    );
    const monthlyMovesBlock = monthly.promptBlock;
    const targetKinds: GluconReportKind[] = kinds?.length
      ? kinds
      : ["activity", "result"];
    const supabase = await createClient();
    const out: GluconDraftRow[] = [];
    const rubricSummary = formatRubricForPrompt(loadScoringRules());

    for (const kind of targetKinds) {
      const ex = await fetchGluconExamples(kind);
      const examples = ex.ok ? ex.examples : [];
      const prompt =
        kind === "activity"
          ? activityPrompt({
              cycle,
              journals,
              examples,
              monthlyMovesBlock,
            })
          : resultPrompt({
              cycle,
              journals,
              examples,
              rubricSummary,
              monthlyMovesBlock,
            });
      const res = await geminiReply(prompt);
      if (!res.ok) {
        return { ok: false, error: res.error };
      }
      const body = res.text.trim();
      const title =
        kind === "activity"
          ? `${cycle.periodKey} 活動報告`
          : `${cycle.periodKey} 成果報告`;
      const status = resolveDraftSaveStatus({ kind, body });

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
            status,
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
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return {
      ok: false,
      error: `下書き生成に失敗しました: ${msg}`,
    };
  }
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

  // posted の再編集は ready へ。queued は維持。成果なしは skipped を維持／復帰。
  const existingStatus =
    existing?.status === "posted" ? "ready" : existing?.status || null;
  const nextStatus = resolveDraftSaveStatus({
    kind,
    body,
    existingStatus,
  });

  const { data, error } = await supabase
    .from("glucon_report_drafts")
    .upsert(
      {
        period_key: periodKey,
        kind,
        title: title?.trim() || existing?.title || `${periodKey} ${kind}`,
        body,
        status: nextStatus,
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

/** 成果報告本文の観点チェック（著者向け。投稿キューには載せない） */
export async function analyzeGluconResultBody(
  body: string,
): Promise<{ ok: boolean; hints?: ResultScoringHints; error?: string }> {
  try {
    return { ok: true, hints: buildResultScoringHints(body) };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, error: msg };
  }
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
  const blocked = queueBlockReason({
    kind,
    body: String(row.body || ""),
    status: String(row.status || ""),
  });
  if (blocked) return { ok: false, error: blocked };

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
  memberHeader: GluconMemberHeaderStatus;
  monthlyDigest: GluconMonthlyDigestPreview | null;
  loadError?: string;
}> {
  const memberHeader = getMemberHeaderStatus();
  try {
    let schedules = await loadGluconSchedules();
    if (!schedules.length) {
      const refreshed = await refreshGluconScheduleFromKamiooya();
      if (!refreshed.ok) {
        // 日程が空でもページは落とさない（手動入力へ誘導）
        return {
          today: ymdJst(),
          cycle: null,
          schedules: [],
          journals: [],
          drafts: [],
          journalSyncedAt: null,
          memberHeader,
          monthlyDigest: null,
          loadError: refreshed.error,
        };
      }
      schedules = await loadGluconSchedules();
    }
    let cycle = pickActiveCycle(schedules);
    schedules = await persistEstimatedCycleIfNeeded(cycle, schedules);
    cycle = pickActiveCycle(schedules);
    const journals = cycle
      ? await loadGluconJournalRange(cycle.journalFrom, cycle.journalTo)
      : [];
    const drafts = cycle ? await loadGluconDrafts(cycle.periodKey) : [];
    let monthlyDigest: GluconMonthlyDigestPreview | null = null;
    if (cycle) {
      try {
        const monthly = await buildGluconMonthlyDigest(
          cycle.journalFrom,
          cycle.journalTo,
        );
        monthlyDigest = {
          from: monthly.from,
          to: monthly.to,
          yoritooriText: monthly.yoritoori.text,
          yoritooriCount: monthly.yoritoori.lines.length,
          yoritooriOk: monthly.yoritoori.ok,
          metricsText: monthly.metrics.text,
          metricsCount: monthly.metrics.rows.length,
          occupancyText: monthly.occupancy.text,
          occupancyCount: monthly.occupancy.events.length,
          notices: monthly.yoritoori.notices,
        };
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        monthlyDigest = {
          from: cycle.journalFrom,
          to: cycle.journalTo,
          yoritooriText: "（集約失敗）",
          yoritooriCount: 0,
          yoritooriOk: false,
          metricsText: "（集約失敗）",
          metricsCount: 0,
          occupancyText: "（集約失敗）",
          occupancyCount: 0,
          notices: [msg.slice(0, 160)],
        };
      }
    }
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
      memberHeader,
      monthlyDigest,
    };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return {
      today: ymdJst(),
      cycle: null,
      schedules: [],
      journals: [],
      drafts: [],
      journalSyncedAt: null,
      memberHeader,
      monthlyDigest: null,
      loadError: msg,
    };
  }
}
