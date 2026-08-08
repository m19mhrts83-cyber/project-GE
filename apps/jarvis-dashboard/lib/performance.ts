/** 仕事／運動パフォーマンス — Journal レンズ */

export type PerformanceLens = "work" | "move";

export type PerformanceJournalRow = {
  recorded_at: string;
  excerpt: string;
  char_count: number;
  sleep_signal?: string | null;
  sleep_tags?: string[] | null;
};

const WORK_RE =
  /残業|深夜作業|深追い|没頭|主要戦果|仕事|出社|在宅|会議|操業|出勤|集中|疲労|疲れ|遅夜/;
const MOVE_RE =
  /ジム|運動|筋トレ|ランニング|散歩|ウォーキング|有酸素|ルーティン|入館|フィットネス|ヨガ/;

export function lensKeywords(lens: PerformanceLens): RegExp {
  return lens === "work" ? WORK_RE : MOVE_RE;
}

export function filterJournalByLens(
  rows: PerformanceJournalRow[],
  lens: PerformanceLens,
): PerformanceJournalRow[] {
  const re = lensKeywords(lens);
  return rows.filter((r) => {
    const blob = `${r.sleep_signal || ""}\n${r.excerpt || ""}`;
    if (re.test(blob)) return true;
    if (lens === "work" && (r.sleep_tags || []).includes("late_work")) {
      return true;
    }
    return false;
  });
}

export function sleepSnippet(excerpt: string, signal?: string | null): string {
  if (signal && signal.trim()) return signal.trim().slice(0, 160);
  const line = (excerpt || "")
    .split("\n")
    .find((l) => l.includes("夜の防衛線") || /就寝|睡眠/.test(l));
  return (line || excerpt || "").trim().slice(0, 160);
}

export const LENS_META: Record<
  PerformanceLens,
  { title: string; subtitle: string; empty: string }
> = {
  work: {
    title: "仕事",
    subtitle:
      "日中のパフォーマンスを ★Journal から見る（残業・集中・主要戦果・疲労など）。診断ではありません。",
    empty:
      "直近に仕事・集中関連の Journal 抜粋がありません。夜の防衛線や主要戦果を書くとここに集まります。",
  },
  move: {
    title: "運動",
    subtitle:
      "ジム・運動・身体活動の記録を ★Journal から見る。診断ではありません。",
    empty:
      "直近に運動・ジム関連の Journal 抜粋がありません。ジム入館や運動メモがあるとここに集まります。",
  },
};
