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
  consultAskPrompt,
  consultRevisePrompt,
  getMemberHeaderStatus,
  resultClarifyPrompt,
  resultFactsPrompt,
  resultPrompt,
} from "@/lib/glucon/prompts";
import {
  buildResultScoringHints,
  formatRubricForPrompt,
  loadScoringRules,
  snapshotScoringFromBody,
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
  GluconClarifyItem,
  GluconConsultTurn,
  GluconDraftPayload,
  GluconDraftRow,
  GluconExample,
  GluconFactItem,
  GluconJournalDay,
  GluconLastResultCoverage,
  GluconMemberHeaderStatus,
  GluconMonthlyDigestPreview,
  GluconReportKind,
  GluconScheduleRow,
  GluconScoringSnapshot,
  ScoringSuggestion,
} from "@/lib/glucon/types";
import { createClient } from "@/lib/supabase/server";

function revalidateGlucon() {
  revalidatePath("/glucon");
}

const YMD_RE = /^\d{4}-\d{2}-\d{2}$/;

function isYmd(s: string | null | undefined): s is string {
  return !!s && YMD_RE.test(s);
}

/** JST で日付文字列の翌日 */
function nextYmd(ymd: string): string {
  const t = Date.parse(`${ymd}T00:00:00+09:00`);
  if (!Number.isFinite(t)) return ymd;
  const d = new Date(t + 86400000);
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(d);
  const y = parts.find((p) => p.type === "year")?.value;
  const m = parts.find((p) => p.type === "month")?.value;
  const day = parts.find((p) => p.type === "day")?.value;
  return `${y}-${m}-${day}`;
}

function resolveCoveredRange(args: {
  cycle: GluconActiveCycle;
  coveredFrom?: string | null;
  coveredTo?: string | null;
  fallbackFrom?: string | null;
  fallbackTo?: string | null;
}): { from: string; to: string; error?: string } {
  const from =
    (isYmd(args.coveredFrom) && args.coveredFrom) ||
    (isYmd(args.fallbackFrom) && args.fallbackFrom) ||
    args.cycle.journalFrom;
  const to =
    (isYmd(args.coveredTo) && args.coveredTo) ||
    (isYmd(args.fallbackTo) && args.fallbackTo) ||
    args.cycle.journalTo;
  if (from > to) {
    return { from, to, error: "対象期間の開始日が終了日より後です" };
  }
  return { from, to };
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

function asPayload(raw: unknown): GluconDraftPayload {
  if (!raw || typeof raw !== "object") return {};
  const o = raw as Record<string, unknown>;
  const facts: GluconFactItem[] = Array.isArray(o.facts)
    ? o.facts
        .filter((x) => x && typeof x === "object")
        .map((x, i) => {
          const f = x as Record<string, unknown>;
          return {
            id: String(f.id || `f${i + 1}`),
            text: String(f.text || ""),
            source: String(f.source || ""),
            resultCandidateTag: f.resultCandidateTag
              ? String(f.resultCandidateTag)
              : null,
            forResult: f.forResult !== false,
          };
        })
    : [];
  const clarify: GluconClarifyItem[] = Array.isArray(o.clarify)
    ? o.clarify
        .filter((x) => x && typeof x === "object")
        .map((x, i) => {
          const c = x as Record<string, unknown>;
          return {
            id: String(c.id || `q${i + 1}`),
            question: String(c.question || ""),
            answer: String(c.answer || ""),
          };
        })
    : [];
  const consult: GluconConsultTurn[] = Array.isArray(o.consult)
    ? o.consult
        .filter((x) => x && typeof x === "object")
        .map((x) => {
          const t = x as Record<string, unknown>;
          return {
            at: String(t.at || new Date().toISOString()),
            mode: t.mode === "revise" ? "revise" : "ask",
            prompt: String(t.prompt || ""),
            reply: String(t.reply || ""),
            revisedBody: t.revisedBody ? String(t.revisedBody) : null,
          };
        })
    : [];
  const phase =
    o.phase === "facts" || o.phase === "clarify" || o.phase === "final"
      ? o.phase
      : undefined;
  return {
    phase,
    facts,
    factsBody: o.factsBody ? String(o.factsBody) : undefined,
    clarify,
    consult,
    resultCandidates: Array.isArray(o.resultCandidates)
      ? o.resultCandidates.map((t) => String(t))
      : undefined,
    covered_from: isYmd(String(o.covered_from || ""))
      ? String(o.covered_from)
      : undefined,
    covered_to: isYmd(String(o.covered_to || ""))
      ? String(o.covered_to)
      : undefined,
    scoring: asScoringSnapshot(o.scoring),
  };
}

function asScoringSnapshot(raw: unknown): GluconScoringSnapshot | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const o = raw as Record<string, unknown>;
  const suggestions: ScoringSuggestion[] = Array.isArray(o.suggestions)
    ? o.suggestions
        .filter((x) => x && typeof x === "object")
        .map((x) => {
          const s = x as Record<string, unknown>;
          return {
            ruleId: String(s.ruleId || ""),
            mid: String(s.mid || ""),
            level: Number(s.level || 0),
            viewpoint: String(s.viewpoint || ""),
            points: Number(s.points || 0),
            matchedKeywords: Array.isArray(s.matchedKeywords)
              ? s.matchedKeywords.map((k) => String(k))
              : [],
          };
        })
    : [];
  const estimated = Number(o.estimated_points);
  if (!Number.isFinite(estimated) && !suggestions.length) return undefined;
  return {
    estimated_points: Number.isFinite(estimated)
      ? estimated
      : suggestions.reduce((sum, s) => sum + (s.points || 0), 0),
    suggestions,
  };
}

function extractJsonObject(text: string): Record<string, unknown> | null {
  const trimmed = text.trim();
  const fence = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/);
  const raw = fence ? fence[1].trim() : trimmed;
  const start = raw.indexOf("{");
  const end = raw.lastIndexOf("}");
  if (start < 0 || end <= start) return null;
  try {
    return JSON.parse(raw.slice(start, end + 1)) as Record<string, unknown>;
  } catch {
    return null;
  }
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
    examples: opts?.includeExamples ? asExamples(row.examples) : [],
    journal_day_count: Number(row.journal_day_count || 0),
    post_error: row.post_error ? String(row.post_error) : null,
    posted_at: row.posted_at ? String(row.posted_at) : null,
    westudy_comment_id: row.westudy_comment_id
      ? String(row.westudy_comment_id)
      : null,
    payload: asPayload(row.payload),
    updated_at: row.updated_at ? String(row.updated_at) : undefined,
  };
}

async function resolveActiveCycle(): Promise<{
  ok: true;
  cycle: GluconActiveCycle;
} | { ok: false; error: string }> {
  const schedules = await loadGluconSchedules();
  let cycle = pickActiveCycle(schedules);
  if (!cycle) {
    const refreshed = await refreshGluconScheduleFromKamiooya();
    if (!refreshed.ok) return { ok: false, error: refreshed.error || "日程取得失敗" };
    cycle = refreshed.cycle || null;
  }
  if (!cycle) {
    return {
      ok: false,
      error:
        "グルコン日程が未設定です。手動で開催日を入力するか、WeStudy取込後に日程更新してください。",
    };
  }
  return { ok: true, cycle };
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

const ARCHIVE_STATUSES = ["posted", "skipped", "queued", "failed"] as const;

/** 過去報告アーカイブ用。当周期の draft/ready は含めない */
export async function loadGluconArchiveDrafts(): Promise<GluconDraftRow[]> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("glucon_report_drafts")
    .select("*")
    .in("status", [...ARCHIVE_STATUSES])
    .order("period_key", { ascending: false });
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
    const resolved = await resolveActiveCycle();
    if (!resolved.ok) return { ok: false, error: resolved.error };
    const cycle = resolved.cycle;

    const journals = await loadGluconJournalRange(
      cycle.journalFrom,
      cycle.journalTo,
    );
    const monthly = await buildGluconMonthlyDigest(
      cycle.journalFrom,
      cycle.journalTo,
    );
    const monthlyMovesBlock = monthly.promptBlock;
    const earlyFillBlock = monthly.occupancy.earlyFillText;
    // 成果優先 → 活動（成果候補を活動から除外）
    const requested: GluconReportKind[] = kinds?.length
      ? kinds
      : ["result", "activity"];
    const targetKinds: GluconReportKind[] = [
      ...(requested.includes("result") ? (["result"] as const) : []),
      ...(requested.includes("activity") ? (["activity"] as const) : []),
    ];
    const supabase = await createClient();
    const out: GluconDraftRow[] = [];
    const rubricSummary = formatRubricForPrompt(loadScoringRules());
    let resultExcludedFacts: string[] = [];

    // 既存成果ドラフトの候補を活動除外に使う
    if (targetKinds.includes("activity") && !targetKinds.includes("result")) {
      const { data: existingResult } = await supabase
        .from("glucon_report_drafts")
        .select("payload")
        .eq("period_key", cycle.periodKey)
        .eq("kind", "result")
        .maybeSingle();
      const pl = asPayload(existingResult?.payload);
      resultExcludedFacts =
        pl.resultCandidates ||
        (pl.facts || [])
          .filter((f) => f.forResult !== false)
          .map((f) => f.text)
          .filter(Boolean);
    }

    for (const kind of targetKinds) {
      const ex = await fetchGluconExamples(kind);
      const examples = ex.ok ? ex.examples : [];
      let payload: GluconDraftPayload = {};

      if (kind === "result") {
        // 一括生成時は事実抽出→最終稿まで一気に（UI ではステップ分割可）
        const factsRes = await geminiReply(
          resultFactsPrompt({
            cycle,
            journals,
            monthlyMovesBlock,
            earlyFillBlock,
            rubricSummary,
          }),
        );
        if (!factsRes.ok) return { ok: false, error: factsRes.error };
        const parsed = extractJsonObject(factsRes.text);
        const facts: GluconFactItem[] = Array.isArray(parsed?.facts)
          ? (parsed!.facts as unknown[])
              .filter((x) => x && typeof x === "object")
              .map((x, i) => {
                const f = x as Record<string, unknown>;
                return {
                  id: String(f.id || `f${i + 1}`),
                  text: String(f.text || ""),
                  source: String(f.source || ""),
                  resultCandidateTag: f.resultCandidateTag
                    ? String(f.resultCandidateTag)
                    : null,
                  forResult: f.forResult !== false,
                };
              })
          : [];
        const factsBody =
          typeof parsed?.factsBody === "string"
            ? parsed.factsBody
            : facts.map((f) => `・${f.text}`).join("\n");
        resultExcludedFacts = facts
          .filter((f) => f.forResult !== false)
          .map((f) => f.text)
          .filter(Boolean);

        const finalRes = await geminiReply(
          resultPrompt({
            cycle,
            journals,
            examples,
            rubricSummary,
            monthlyMovesBlock,
            earlyFillBlock,
            facts,
            factsBody,
          }),
        );
        if (!finalRes.ok) return { ok: false, error: finalRes.error };
        const body = finalRes.text.trim();
        payload = {
          phase: "final",
          facts,
          factsBody,
          clarify: [],
          consult: [],
          resultCandidates: resultExcludedFacts,
        };
        const title = `${cycle.periodKey} 成果報告`;
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
              payload,
              updated_at: new Date().toISOString(),
            },
            { onConflict: "period_key,kind" },
          )
          .select("*")
          .maybeSingle();
        if (error) return { ok: false, error: error.message };
        if (data) out.push(mapDraft(data as Record<string, unknown>));
        continue;
      }

      const prompt = activityPrompt({
        cycle,
        journals,
        examples,
        monthlyMovesBlock,
        resultExcludedFacts,
      });
      const res = await geminiReply(prompt);
      if (!res.ok) return { ok: false, error: res.error };
      const body = res.text.trim();
      const title = `${cycle.periodKey} 活動報告`;
      const status = resolveDraftSaveStatus({ kind, body });
      const { data: existingAct } = await supabase
        .from("glucon_report_drafts")
        .select("payload")
        .eq("period_key", cycle.periodKey)
        .eq("kind", "activity")
        .maybeSingle();
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
            payload: asPayload(existingAct?.payload),
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

/** 投稿済み成果報告から前回の covered 期間を取得 */
export async function getLastResultCoverage(): Promise<GluconLastResultCoverage | null> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("glucon_report_drafts")
    .select("period_key,posted_at,payload")
    .eq("kind", "result")
    .eq("status", "posted")
    .order("posted_at", { ascending: false })
    .limit(20);
  if (!data?.length) return null;

  let best: GluconLastResultCoverage | null = null;
  for (const row of data) {
    const pl = asPayload(row.payload);
    const to = pl.covered_to || null;
    if (!to) continue;
    if (!best || (best.covered_to && to > best.covered_to) || !best.covered_to) {
      best = {
        covered_from: pl.covered_from || null,
        covered_to: to,
        posted_at: row.posted_at ? String(row.posted_at) : null,
        period_key: row.period_key ? String(row.period_key) : null,
      };
    }
  }
  // covered_to が無い古い投稿は posted_at の日付を近似に使う
  if (!best && data[0]) {
    const posted = data[0].posted_at ? String(data[0].posted_at).slice(0, 10) : null;
    return {
      covered_from: null,
      covered_to: posted,
      posted_at: data[0].posted_at ? String(data[0].posted_at) : null,
      period_key: data[0].period_key ? String(data[0].period_key) : null,
    };
  }
  return best;
}

/** Step1: 成果報告の事実のみ下書き */
export async function generateGluconFacts(opts?: {
  coveredFrom?: string;
  coveredTo?: string;
}): Promise<{
  ok: boolean;
  error?: string;
  draft?: GluconDraftRow;
}> {
  try {
    const resolved = await resolveActiveCycle();
    if (!resolved.ok) return { ok: false, error: resolved.error };
    const cycle = resolved.cycle;
    const last = await getLastResultCoverage();
    const defaultFrom = last?.covered_to
      ? nextYmd(last.covered_to)
      : cycle.journalFrom;
    const range = resolveCoveredRange({
      cycle,
      coveredFrom: opts?.coveredFrom,
      coveredTo: opts?.coveredTo,
      fallbackFrom: defaultFrom,
      fallbackTo: ymdJst(),
    });
    if (range.error) return { ok: false, error: range.error };

    const journals = await loadGluconJournalRange(range.from, range.to);
    const monthly = await buildGluconMonthlyDigest(range.from, range.to);
    const rubricSummary = formatRubricForPrompt(loadScoringRules());
    const res = await geminiReply(
      resultFactsPrompt({
        cycle,
        journals,
        monthlyMovesBlock: monthly.promptBlock,
        earlyFillBlock: monthly.occupancy.earlyFillText,
        rubricSummary,
      }),
    );
    if (!res.ok) return { ok: false, error: res.error };
    const parsed = extractJsonObject(res.text);
    const facts: GluconFactItem[] = Array.isArray(parsed?.facts)
      ? (parsed!.facts as unknown[])
          .filter((x) => x && typeof x === "object")
          .map((x, i) => {
            const f = x as Record<string, unknown>;
            return {
              id: String(f.id || `f${i + 1}`),
              text: String(f.text || ""),
              source: String(f.source || ""),
              resultCandidateTag: f.resultCandidateTag
                ? String(f.resultCandidateTag)
                : null,
              forResult: f.forResult !== false,
            };
          })
      : [];
    const factsBody =
      typeof parsed?.factsBody === "string"
        ? parsed.factsBody
        : facts.map((f) => `・${f.text}`).join("\n");
    const resultCandidates = facts
      .filter((f) => f.forResult !== false)
      .map((f) => f.text)
      .filter(Boolean);
    const body = factsBody.trim() || "（抽出できる事実なし）";
    const payload: GluconDraftPayload = {
      phase: "facts",
      facts,
      factsBody: body,
      clarify: [],
      consult: [],
      resultCandidates,
      covered_from: range.from,
      covered_to: range.to,
    };
    const supabase = await createClient();
    const { data: prevRow } = await supabase
      .from("glucon_report_drafts")
      .select("payload")
      .eq("period_key", cycle.periodKey)
      .eq("kind", "result")
      .maybeSingle();
    const prevPl = asPayload(prevRow?.payload);
    if (prevPl.consult?.length) payload.consult = prevPl.consult;

    const { data, error } = await supabase
      .from("glucon_report_drafts")
      .upsert(
        {
          period_key: cycle.periodKey,
          kind: "result",
          glucon_date: cycle.gluconDate,
          report_deadline: cycle.reportDeadline,
          title: `${cycle.periodKey} 成果報告`,
          body,
          status: "draft",
          journal_day_count: journals.length,
          post_error: null,
          payload,
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
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, error: msg };
  }
}

/** Step2: 確認質問を生成 */
export async function generateGluconClarify(): Promise<{
  ok: boolean;
  error?: string;
  draft?: GluconDraftRow;
}> {
  try {
    const resolved = await resolveActiveCycle();
    if (!resolved.ok) return { ok: false, error: resolved.error };
    const cycle = resolved.cycle;
    const supabase = await createClient();
    const { data: row } = await supabase
      .from("glucon_report_drafts")
      .select("*")
      .eq("period_key", cycle.periodKey)
      .eq("kind", "result")
      .maybeSingle();
    if (!row) return { ok: false, error: "先に事実下書きを生成してください" };
    const pl = asPayload(row.payload);
    const facts = pl.facts || [];
    const factsBody = pl.factsBody || String(row.body || "");
    const res = await geminiReply(
      resultClarifyPrompt({ cycle, facts, factsBody }),
    );
    if (!res.ok) return { ok: false, error: res.error };
    const parsed = extractJsonObject(res.text);
    const questions = Array.isArray(parsed?.questions)
      ? (parsed!.questions as unknown[])
          .filter((x) => x && typeof x === "object")
          .map((x, i) => {
            const q = x as Record<string, unknown>;
            return {
              id: String(q.id || `q${i + 1}`),
              question: String(q.question || ""),
              answer: "",
            };
          })
      : [];
    const payload: GluconDraftPayload = {
      ...pl,
      phase: "clarify",
      clarify: questions.length
        ? questions
        : [
            {
              id: "q1",
              question: "苦労した点・工夫した点があれば教えてください",
              answer: "",
            },
            {
              id: "q2",
              question: "入会前と入会後で変わった点はありますか？",
              answer: "",
            },
          ],
    };
    const { data, error } = await supabase
      .from("glucon_report_drafts")
      .update({
        payload,
        updated_at: new Date().toISOString(),
      })
      .eq("period_key", cycle.periodKey)
      .eq("kind", "result")
      .select("*")
      .maybeSingle();
    if (error) return { ok: false, error: error.message };
    revalidateGlucon();
    return {
      ok: true,
      draft: data ? mapDraft(data as Record<string, unknown>) : undefined,
    };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, error: msg };
  }
}

export async function saveGluconClarifyAnswers(
  answers: { id: string; answer: string }[],
): Promise<{ ok: boolean; error?: string; draft?: GluconDraftRow }> {
  try {
    const resolved = await resolveActiveCycle();
    if (!resolved.ok) return { ok: false, error: resolved.error };
    const cycle = resolved.cycle;
    const supabase = await createClient();
    const { data: row } = await supabase
      .from("glucon_report_drafts")
      .select("*")
      .eq("period_key", cycle.periodKey)
      .eq("kind", "result")
      .maybeSingle();
    if (!row) return { ok: false, error: "下書きがありません" };
    const pl = asPayload(row.payload);
    const byId = new Map(answers.map((a) => [a.id, a.answer]));
    const clarify = (pl.clarify || []).map((c) => ({
      ...c,
      answer: byId.has(c.id) ? String(byId.get(c.id) || "") : c.answer,
    }));
    const payload: GluconDraftPayload = { ...pl, clarify, phase: "clarify" };
    const { data, error } = await supabase
      .from("glucon_report_drafts")
      .update({ payload, updated_at: new Date().toISOString() })
      .eq("period_key", cycle.periodKey)
      .eq("kind", "result")
      .select("*")
      .maybeSingle();
    if (error) return { ok: false, error: error.message };
    revalidateGlucon();
    return {
      ok: true,
      draft: data ? mapDraft(data as Record<string, unknown>) : undefined,
    };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, error: msg };
  }
}

/** Step3: 最終稿生成 */
export async function generateGluconFinal(opts?: {
  coveredFrom?: string;
  coveredTo?: string;
}): Promise<{
  ok: boolean;
  error?: string;
  draft?: GluconDraftRow;
}> {
  try {
    const resolved = await resolveActiveCycle();
    if (!resolved.ok) return { ok: false, error: resolved.error };
    const cycle = resolved.cycle;
    const supabase = await createClient();
    const { data: row } = await supabase
      .from("glucon_report_drafts")
      .select("*")
      .eq("period_key", cycle.periodKey)
      .eq("kind", "result")
      .maybeSingle();
    if (!row) return { ok: false, error: "先に事実下書きを生成してください" };
    const pl = asPayload(row.payload);
    const range = resolveCoveredRange({
      cycle,
      coveredFrom: opts?.coveredFrom || pl.covered_from,
      coveredTo: opts?.coveredTo || pl.covered_to,
      fallbackFrom: cycle.journalFrom,
      fallbackTo: cycle.journalTo,
    });
    if (range.error) return { ok: false, error: range.error };

    const journals = await loadGluconJournalRange(range.from, range.to);
    const monthly = await buildGluconMonthlyDigest(range.from, range.to);
    const ex = await fetchGluconExamples("result");
    const examples = ex.ok ? ex.examples : [];
    const rubricSummary = formatRubricForPrompt(loadScoringRules());
    const res = await geminiReply(
      resultPrompt({
        cycle,
        journals,
        examples,
        rubricSummary,
        monthlyMovesBlock: monthly.promptBlock,
        earlyFillBlock: monthly.occupancy.earlyFillText,
        facts: pl.facts,
        factsBody: pl.factsBody,
        clarify: pl.clarify,
      }),
    );
    if (!res.ok) return { ok: false, error: res.error };
    const body = res.text.trim();
    const status = resolveDraftSaveStatus({ kind: "result", body });
    const payload: GluconDraftPayload = {
      ...pl,
      phase: "final",
      covered_from: range.from,
      covered_to: range.to,
      resultCandidates:
        pl.resultCandidates ||
        (pl.facts || [])
          .filter((f) => f.forResult !== false)
          .map((f) => f.text)
          .filter(Boolean),
    };
    const { data, error } = await supabase
      .from("glucon_report_drafts")
      .update({
        body,
        status,
        examples,
        journal_day_count: journals.length,
        payload,
        post_error: null,
        updated_at: new Date().toISOString(),
      })
      .eq("period_key", cycle.periodKey)
      .eq("kind", "result")
      .select("*")
      .maybeSingle();
    if (error) return { ok: false, error: error.message };
    revalidateGlucon();
    return {
      ok: true,
      draft: data ? mapDraft(data as Record<string, unknown>) : undefined,
    };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, error: msg };
  }
}

/** 聞く／直す */
export async function consultGluconDraft(args: {
  kind: GluconReportKind;
  mode: "ask" | "revise";
  prompt: string;
  body: string;
}): Promise<{
  ok: boolean;
  error?: string;
  reply?: string;
  revisedBody?: string;
  draft?: GluconDraftRow;
}> {
  try {
    const q = args.prompt.trim();
    if (!q) return { ok: false, error: "質問または指示を入力してください" };
    const resolved = await resolveActiveCycle();
    if (!resolved.ok) return { ok: false, error: resolved.error };
    const cycle = resolved.cycle;
    const gemini =
      args.mode === "ask"
        ? await geminiReply(
            consultAskPrompt({
              body: args.body,
              question: q,
              kind: args.kind,
            }),
          )
        : await geminiReply(
            consultRevisePrompt({
              body: args.body,
              instruction: q,
              kind: args.kind,
            }),
          );
    if (!gemini.ok) return { ok: false, error: gemini.error };
    const reply = gemini.text.trim();
    const revisedBody = args.mode === "revise" ? reply : undefined;
    const supabase = await createClient();
    const { data: row } = await supabase
      .from("glucon_report_drafts")
      .select("*")
      .eq("period_key", cycle.periodKey)
      .eq("kind", args.kind)
      .maybeSingle();
    const pl = asPayload(row?.payload);
    const turn: GluconConsultTurn = {
      at: new Date().toISOString(),
      mode: args.mode,
      prompt: q,
      reply: args.mode === "ask" ? reply : "（修正案を提示）",
      revisedBody: revisedBody || null,
    };
    const consult = [...(pl.consult || []), turn].slice(-20);
    const payload: GluconDraftPayload = { ...pl, consult };
    if (!row) {
      return { ok: true, reply, revisedBody };
    }
    const { data, error } = await supabase
      .from("glucon_report_drafts")
      .update({ payload, updated_at: new Date().toISOString() })
      .eq("period_key", cycle.periodKey)
      .eq("kind", args.kind)
      .select("*")
      .maybeSingle();
    if (error) return { ok: false, error: error.message };
    revalidateGlucon();
    return {
      ok: true,
      reply: args.mode === "ask" ? reply : "修正案を用意しました。反映できます。",
      revisedBody,
      draft: data ? mapDraft(data as Record<string, unknown>) : undefined,
    };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { ok: false, error: msg };
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
        payload: asPayload(existing?.payload),
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
  opts?: { coveredFrom?: string; coveredTo?: string },
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

  const pl = asPayload(row.payload);
  const payload: GluconDraftPayload = { ...pl };
  if (kind === "result") {
    if (isYmd(opts?.coveredFrom)) payload.covered_from = opts!.coveredFrom;
    else if (!payload.covered_from) {
      /* keep */
    }
    if (isYmd(opts?.coveredTo)) payload.covered_to = opts!.coveredTo;
    // 投稿キュー投入時に期間が無ければサイクル相当を確定
    if (!payload.covered_from && row.report_deadline) {
      // leave as-is; UI should have set it
    }
    if (!payload.covered_to) {
      payload.covered_to = ymdJst();
    }
    payload.scoring = snapshotScoringFromBody(String(row.body || ""));
  }

  const { error } = await supabase
    .from("glucon_report_drafts")
    .update({
      status: "queued",
      post_error: null,
      payload,
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
  lastResultCoverage: GluconLastResultCoverage | null;
  archiveDrafts: GluconDraftRow[];
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
          lastResultCoverage: null,
          archiveDrafts: [],
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
          earlyFills: monthly.occupancy.earlyFills,
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
          earlyFills: [],
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
    const lastResultCoverage = await getLastResultCoverage();
    const archiveDrafts = await loadGluconArchiveDrafts();

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
      lastResultCoverage,
      archiveDrafts,
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
      lastResultCoverage: null,
      archiveDrafts: [],
      loadError: msg,
    };
  }
}
