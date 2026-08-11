/** グルコン報告のアーカイブ集計・連続・目安点 */

import { snapshotScoringFromBody } from "./scoring";
import type {
  GluconDraftRow,
  GluconDraftStatus,
  GluconReportKind,
} from "./types";

const ARCHIVE_STATUSES = new Set<GluconDraftStatus>([
  "posted",
  "skipped",
  "queued",
  "failed",
]);

const ACHIEVED_STATUSES = new Set<GluconDraftStatus>(["posted", "skipped"]);

export type GluconArchiveKindView = {
  kind: GluconReportKind;
  status: GluconDraftStatus;
  body: string;
  postedAt: string | null;
  westudyCommentId: string | null;
  estimatedPoints: number;
};

export type GluconArchiveMonth = {
  periodKey: string;
  gluconDate: string | null;
  reportDeadline: string | null;
  activity: GluconArchiveKindView | null;
  result: GluconArchiveKindView | null;
  estimatedPoints: number;
};

export type GluconHabitDot = {
  periodKey: string;
  state: "achieved" | "missed" | "pending" | "future";
};

export type GluconTrendPoint = {
  periodKey: string;
  activityPosted: number;
  resultPosted: number;
  points: number;
  cumulativePoints: number;
};

export type GluconMotivationStats = {
  currentStreak: number;
  longestStreak: number;
  postedMonths: number;
  estimatedPointsTotal: number;
  habitDots: GluconHabitDot[];
  trend: GluconTrendPoint[];
};

const PERIOD_RE = /^(\d{4})-(\d{2})$/;

export function isArchiveStatus(status: GluconDraftStatus): boolean {
  return ARCHIVE_STATUSES.has(status);
}

export function addMonths(periodKey: string, delta: number): string {
  const m = PERIOD_RE.exec(periodKey);
  if (!m) return periodKey;
  const y = Number(m[1]);
  const mo = Number(m[2]) - 1 + delta;
  const d = new Date(Date.UTC(y, mo, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

export function estimatedPointsForResult(row: GluconDraftRow): number {
  if (row.kind !== "result") return 0;
  const snap = row.payload.scoring;
  if (snap && Number.isFinite(snap.estimated_points)) {
    return snap.estimated_points;
  }
  return snapshotScoringFromBody(row.body).estimated_points;
}

function toKindView(row: GluconDraftRow): GluconArchiveKindView {
  return {
    kind: row.kind,
    status: row.status,
    body: row.body || "",
    postedAt: row.posted_at,
    westudyCommentId: row.westudy_comment_id,
    estimatedPoints: estimatedPointsForResult(row),
  };
}

export function groupArchiveByPeriod(drafts: GluconDraftRow[]): GluconArchiveMonth[] {
  const byPeriod = new Map<string, GluconDraftRow[]>();
  for (const row of drafts) {
    if (!isArchiveStatus(row.status)) continue;
    const list = byPeriod.get(row.period_key) || [];
    list.push(row);
    byPeriod.set(row.period_key, list);
  }
  const keys = [...byPeriod.keys()].sort((a, b) => b.localeCompare(a));
  return keys.map((periodKey) => {
    const rows = byPeriod.get(periodKey) || [];
    const activityRow = rows.find((r) => r.kind === "activity") || null;
    const resultRow = rows.find((r) => r.kind === "result") || null;
    const activity = activityRow ? toKindView(activityRow) : null;
    const result = resultRow ? toKindView(resultRow) : null;
    return {
      periodKey,
      gluconDate: activityRow?.glucon_date || resultRow?.glucon_date || null,
      reportDeadline:
        activityRow?.report_deadline || resultRow?.report_deadline || null,
      activity,
      result,
      estimatedPoints: result?.estimatedPoints || 0,
    };
  });
}

function isAchieved(activity: GluconDraftRow | undefined): boolean {
  return !!activity && ACHIEVED_STATUSES.has(activity.status);
}

function isPosted(row: GluconDraftRow | undefined): boolean {
  return row?.status === "posted";
}

function monthsBetween(fromKey: string, toKey: string): string[] {
  if (!PERIOD_RE.test(fromKey) || !PERIOD_RE.test(toKey)) return [];
  const out: string[] = [];
  let cur = fromKey;
  let guard = 0;
  while (cur <= toKey && guard < 240) {
    out.push(cur);
    cur = addMonths(cur, 1);
    guard += 1;
  }
  return out;
}

export function buildGluconMotivation(args: {
  drafts: GluconDraftRow[];
  currentPeriodKey: string | null;
  today: string;
  reportDeadline: string | null;
}): GluconMotivationStats {
  const currentPeriodKey =
    args.currentPeriodKey || (args.today || "").slice(0, 7);
  const activityByPeriod = new Map<string, GluconDraftRow>();
  const resultByPeriod = new Map<string, GluconDraftRow>();
  for (const row of args.drafts) {
    if (row.kind === "activity") activityByPeriod.set(row.period_key, row);
    if (row.kind === "result") resultByPeriod.set(row.period_key, row);
  }

  const knownKeys = [
    ...new Set([...activityByPeriod.keys(), ...resultByPeriod.keys()]),
  ].sort();
  const firstKey = knownKeys[0] || currentPeriodKey;
  const lastKey =
    currentPeriodKey && currentPeriodKey >= (knownKeys[knownKeys.length - 1] || "")
      ? currentPeriodKey
      : knownKeys[knownKeys.length - 1] || currentPeriodKey;
  const allMonths = monthsBetween(firstKey, lastKey);

  const achievedSet = new Set<string>();
  for (const key of allMonths) {
    if (isAchieved(activityByPeriod.get(key))) achievedSet.add(key);
  }

  const postedMonths = [...achievedSet].length;

  let longestStreak = 0;
  let run = 0;
  for (const key of allMonths) {
    if (achievedSet.has(key)) {
      run += 1;
      if (run > longestStreak) longestStreak = run;
    } else {
      run = 0;
    }
  }

  const deadlinePassed =
    !!args.reportDeadline && args.today > args.reportDeadline;
  const currentDone = achievedSet.has(currentPeriodKey);
  let streakStart = currentPeriodKey;
  if (!currentDone && !deadlinePassed) {
    streakStart = addMonths(currentPeriodKey, -1);
  }
  let currentStreak = 0;
  let cursor = streakStart;
  for (let i = 0; i < 120; i++) {
    if (!achievedSet.has(cursor)) break;
    currentStreak += 1;
    cursor = addMonths(cursor, -1);
  }

  const habitFrom = addMonths(currentPeriodKey, -11);
  const habitMonths = monthsBetween(habitFrom, addMonths(currentPeriodKey, 0));
  const habitDots: GluconHabitDot[] = habitMonths.map((periodKey) => {
    if (periodKey > currentPeriodKey) {
      return { periodKey, state: "future" };
    }
    if (achievedSet.has(periodKey)) {
      return { periodKey, state: "achieved" };
    }
    if (periodKey === currentPeriodKey && !deadlinePassed) {
      return { periodKey, state: "pending" };
    }
    return { periodKey, state: "missed" };
  });

  const trendMonths = habitMonths;
  let cumulative = 0;
  const trend: GluconTrendPoint[] = trendMonths.map((periodKey) => {
    const activity = activityByPeriod.get(periodKey);
    const result = resultByPeriod.get(periodKey);
    const points = result ? estimatedPointsForResult(result) : 0;
    cumulative += points;
    return {
      periodKey,
      activityPosted: isPosted(activity) ? 1 : 0,
      resultPosted: isPosted(result) ? 1 : 0,
      points,
      cumulativePoints: cumulative,
    };
  });

  const estimatedPointsTotal = [...resultByPeriod.values()].reduce(
    (sum, row) => sum + estimatedPointsForResult(row),
    0,
  );

  return {
    currentStreak,
    longestStreak,
    postedMonths,
    estimatedPointsTotal,
    habitDots,
    trend,
  };
}
