import raw from "@/config/uiux_scorecard.json";

/** UI/UX採点表（config/uiux_scorecard.json）の読み出しと計算 */

export type Region = "world" | "japan";
export const REGIONS: Region[] = ["world", "japan"];
export const REGION_LABEL: Record<Region, string> = { world: "世界", japan: "日本" };

export type Axis = { key: string; label: string; question: string; world_bar: string; japan_bar: string };
export type AppDef = { key: string; label: string; href: string };
export type Benchmark = { name: string; url: string };
/** target_region が目標。もう一方の地域の点は参考線（一流水準）として表示する */
export type Goal = { set_on: string; review_on: string; target_region: Region; world: number; japan: number; note?: string };
export type Improvement = { axis: string; gap: string; next: string };
export type Evaluation = {
  date: string;
  method: string;
  by?: string;
  scores: Record<string, Record<Region, Record<string, number>>>;
  improvements: Record<string, Improvement[]>;
};
export type Scorecard = {
  apps: AppDef[];
  axes: Axis[];
  benchmarks: Record<Region, Benchmark[]>;
  goals: Goal[];
  evaluations: Evaluation[];
};

export const scorecard = raw as unknown as Scorecard;

/** 項目0〜10の合計を100点換算（未採点の項目は除いて割る） */
export function total(axisScores: Record<string, number> | undefined, axes: Axis[] = scorecard.axes): number | null {
  if (!axisScores) return null;
  const vals = axes.map((a) => axisScores[a.key]).filter((v): v is number => typeof v === "number");
  if (!vals.length) return null;
  return Math.round((vals.reduce((s, v) => s + v, 0) / (vals.length * 10)) * 100);
}

/** その日に有効なゴール（set_on が date 以前で最も新しいもの） */
export function goalAt(date: string, goals: Goal[] = scorecard.goals): Goal | null {
  const ok = goals.filter((g) => g.set_on <= date).sort((a, b) => a.set_on.localeCompare(b.set_on));
  return ok[ok.length - 1] ?? null;
}

export function sortedEvaluations(evals: Evaluation[] = scorecard.evaluations): Evaluation[] {
  return [...evals].sort((a, b) => a.date.localeCompare(b.date));
}

/** アプリ×地域の点数の推移（古い順） */
export function history(appKey: string, region: Region, evals: Evaluation[] = sortedEvaluations()): { date: string; score: number }[] {
  const out: { date: string; score: number }[] = [];
  for (const e of evals) {
    const t = total(e.scores[appKey]?.[region]);
    if (t != null) out.push({ date: e.date, score: t });
  }
  return out;
}

export function todayJst(now = new Date()): string {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Tokyo" }).format(now);
}
