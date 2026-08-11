/** 神大家4.グルコン lesson_title から開催日・提出期限・Journal レンジを算出 */

import type {
  GluconActiveCycle,
  GluconScheduleRow,
  GluconScheduleSource,
} from "./types";

const TITLE_DATE_RE =
  /(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*グルコン/;

export function ymdJst(d = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

export function parseGluconTitleDate(
  lessonTitle: string,
): { ymd: string; title: string } | null {
  const m = TITLE_DATE_RE.exec(lessonTitle || "");
  if (!m) return null;
  const y = Number(m[1]);
  const mo = Number(m[2]);
  const d = Number(m[3]);
  if (!y || mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  const ymd = `${y}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
  const title = (lessonTitle || "").replace(/\s+/g, " ").trim().slice(0, 180);
  return { ymd, title };
}

export function addDaysYmd(ymd: string, delta: number): string {
  const [y, m, d] = ymd.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + delta);
  return dt.toISOString().slice(0, 10);
}

export function reportDeadlineFromGluconDate(gluconDate: string): string {
  return addDaysYmd(gluconDate, -10);
}

export function periodKeyFromGluconDate(gluconDate: string): string {
  return gluconDate.slice(0, 7);
}

/** YYYY-MM の翌月 */
export function nextPeriodKey(periodKey: string): string {
  const [ys, ms] = periodKey.split("-");
  const y = Number(ys);
  const m = Number(ms);
  if (!y || !m) return periodKey;
  const nm = m === 12 ? 1 : m + 1;
  const ny = m === 12 ? y + 1 : y;
  return `${ny}-${String(nm).padStart(2, "0")}`;
}

export function daysBetween(fromYmd: string, toYmd: string): number {
  const a = new Date(`${fromYmd}T00:00:00+09:00`).getTime();
  const b = new Date(`${toYmd}T00:00:00+09:00`).getTime();
  return Math.round((b - a) / (1000 * 60 * 60 * 24));
}

export type ParsedLesson = {
  glucon_date: string;
  report_deadline: string;
  title: string;
  comment_id: string | null;
  source: GluconScheduleSource;
};

export function lessonsToScheduleRows(
  rows: Array<{
    comment_id?: string | null;
    lesson_title?: string | null;
  }>,
): ParsedLesson[] {
  const byDate = new Map<string, ParsedLesson>();
  for (const r of rows) {
    const parsed = parseGluconTitleDate(r.lesson_title || "");
    if (!parsed) continue;
    const prev = byDate.get(parsed.ymd);
    if (prev && (prev.title?.length || 0) >= parsed.title.length) continue;
    byDate.set(parsed.ymd, {
      glucon_date: parsed.ymd,
      report_deadline: reportDeadlineFromGluconDate(parsed.ymd),
      title: parsed.title,
      comment_id: r.comment_id || null,
      source: "scraped",
    });
  }
  return [...byDate.values()].sort((a, b) =>
    a.glucon_date.localeCompare(b.glucon_date),
  );
}

/** 前回開催 + 約30日の推定（レッスン未掲載時） */
export function estimateNextFromLast(
  lastGluconDate: string,
  today = ymdJst(),
): ParsedLesson {
  let candidate = addDaysYmd(lastGluconDate, 30);
  // 月末付近に寄せる: 候補月の最終日に近い日曜相当は複雑なので +30 固定
  if (candidate <= today) {
    candidate = addDaysYmd(today, 20);
  }
  return {
    glucon_date: candidate,
    report_deadline: reportDeadlineFromGluconDate(candidate),
    title: `推定: 前回 ${lastGluconDate} の約30日後`,
    comment_id: null,
    source: "estimated",
  };
}

export function pickActiveCycle(
  schedules: GluconScheduleRow[],
  today = ymdJst(),
): GluconActiveCycle | null {
  if (!schedules.length) return null;
  const sorted = [...schedules].sort((a, b) =>
    a.glucon_date.localeCompare(b.glucon_date),
  );

  let upcoming = sorted.find((s) => s.glucon_date >= today);
  let estimated = false;
  if (!upcoming) {
    const last = sorted[sorted.length - 1];
    const est = estimateNextFromLast(last.glucon_date, today);
    upcoming = {
      glucon_date: est.glucon_date,
      report_deadline: est.report_deadline,
      title: est.title,
      source: "estimated",
      comment_id: null,
    };
    estimated = true;
  }

  const idx = sorted.findIndex((s) => s.glucon_date === upcoming!.glucon_date);
  const prev =
    idx > 0
      ? sorted[idx - 1]
      : sorted.filter((s) => s.glucon_date < upcoming!.glucon_date).at(-1) ||
        null;

  const prevDeadline = prev?.report_deadline || null;
  const journalFrom = prevDeadline || `${upcoming.glucon_date.slice(0, 7)}-01`;
  const journalTo = upcoming.report_deadline;

  return {
    gluconDate: upcoming.glucon_date,
    reportDeadline: upcoming.report_deadline,
    periodKey: periodKeyFromGluconDate(upcoming.glucon_date),
    title: upcoming.title,
    source: upcoming.source,
    prevDeadline,
    journalFrom,
    journalTo,
    daysUntilDeadline: daysBetween(today, upcoming.report_deadline),
    estimated: estimated || upcoming.source === "estimated",
  };
}

/** 現サイクル開催の翌日以降に切り替わる次開催の目安 */
export function peekNextCycle(
  current: GluconActiveCycle,
): {
  availableFrom: string;
  gluconDate: string;
  reportDeadline: string;
  periodKey: string;
} {
  const availableFrom = addDaysYmd(current.gluconDate, 1);
  const est = estimateNextFromLast(current.gluconDate, availableFrom);
  return {
    availableFrom,
    gluconDate: est.glucon_date,
    reportDeadline: est.report_deadline,
    periodKey: periodKeyFromGluconDate(est.glucon_date),
  };
}

export function mergeManualOverride(
  schedules: GluconScheduleRow[],
  manualDate: string,
  title = "",
): GluconScheduleRow[] {
  const deadline = reportDeadlineFromGluconDate(manualDate);
  const row: GluconScheduleRow = {
    glucon_date: manualDate,
    report_deadline: deadline,
    title: title || `手動: ${manualDate} グルコン`,
    source: "manual",
    comment_id: null,
  };
  const others = schedules.filter((s) => s.glucon_date !== manualDate);
  return [...others, row].sort((a, b) =>
    a.glucon_date.localeCompare(b.glucon_date),
  );
}
