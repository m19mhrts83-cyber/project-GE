import raw from "@/config/agent_maturity.json";
import { createServiceClient } from "@/lib/supabase/admin";

/**
 * AIエージェント運用成熟度。物差し（線・ゴール・改善案）は config/agent_maturity.json、
 * 実測値は Supabase agent_maturity_snapshots（scripts/jarvis_agent_maturity.py が土曜に追加）。
 * 取れない指標はレベルを付けず「未計測」。平均にも入れない（推測で埋めない）。
 */

export type MetricDef = {
  label: string;
  unit: "ratio" | "count" | "yen" | "score";
  dir: "up" | "down";
  levels: [number, number, number, number];
  min_n?: number;
  source: string;
};
export type ItemDef = { key: string; label: string; world: string; metrics: string[]; actions: string[] };
export type AxisDef = { key: "process" | "output"; label: string; items: ItemDef[] };
export type MaturityGoal = { set_on: string; review_on: string; process: number; output: number; note?: string };
export type MaturityConfig = {
  level_labels: Record<string, string>;
  goals: MaturityGoal[];
  axes: AxisDef[];
  metrics: Record<string, MetricDef>;
};
export const maturityConfig = raw as unknown as MaturityConfig;

export type MetricValue = { value: number; num?: number; den?: number; note?: string };
export type SnapshotMetrics = Record<string, MetricValue> & { _missing?: Record<string, string> };
export type Snapshot = { measured_on: string; scope: string; metrics: SnapshotMetrics };

/** 実測値 → L1〜L5（levels は L2〜L5 に上がる境目） */
export function metricLevel(def: MetricDef, v: number): number {
  let lv = 1;
  def.levels.forEach((th, i) => {
    if (def.dir === "up" ? v >= th : v <= th) lv = i + 2;
  });
  return lv;
}

export function metricValue(s: Snapshot | null | undefined, key: string): MetricValue | null {
  const m = s?.metrics?.[key] as MetricValue | undefined;
  return m && typeof m.value === "number" ? m : null;
}

/** 項目のレベル = 計測できた指標のレベルの平均（小数1桁）。全部未計測なら null */
export function itemLevel(item: ItemDef, s: Snapshot | null | undefined, cfg = maturityConfig): number | null {
  const lvs = item.metrics
    .map((k) => {
      const v = metricValue(s, k);
      const d = cfg.metrics[k];
      return v && d ? metricLevel(d, v.value) : null;
    })
    .filter((x): x is number => x != null);
  if (!lvs.length) return null;
  return Math.round((lvs.reduce((a, b) => a + b, 0) / lvs.length) * 10) / 10;
}

export function axisLevel(axis: AxisDef, s: Snapshot | null | undefined): { level: number | null; measured: number; total: number } {
  const lvs = axis.items.map((it) => itemLevel(it, s)).filter((x): x is number => x != null);
  return {
    level: lvs.length ? Math.round((lvs.reduce((a, b) => a + b, 0) / lvs.length) * 10) / 10 : null,
    measured: lvs.length,
    total: axis.items.length,
  };
}

export function formatMetric(def: MetricDef, v: MetricValue): string {
  const n = v.den != null ? `（${v.num}/${v.den}）` : "";
  if (def.unit === "ratio") return `${Math.round(v.value * 100)}%${n}`;
  if (def.unit === "yen") return `${Math.round(v.value).toLocaleString("ja-JP")}円${n}`;
  if (def.unit === "score") return `${v.value}点`;
  return `${v.value}件${n}`;
}

export function missingReason(s: Snapshot | null | undefined, key: string): string {
  return s?.metrics?._missing?.[key] || (s ? "記録なし" : "まだ計測していない");
}

export type Priority = { axis: AxisDef; item: ItemDef; level: number | null; prev: number | null; action: string; why: string };

/**
 * 優先改善: レベルが低い順・前回より下がった順に2件＋未計測の項目から1件（「計測できるようにする」改善案）。
 * 改善案は config の固定文から選ぶ（AIで毎回作らない）。
 */
export function priorities(latest: Snapshot | null, prev: Snapshot | null, n = 3): Priority[] {
  const all: Priority[] = [];
  for (const axis of maturityConfig.axes) {
    for (const item of axis.items) {
      const level = itemLevel(item, latest);
      const p = itemLevel(item, prev);
      const why =
        level == null
          ? `未計測：${item.metrics.map((k) => missingReason(latest, k)).join("／")}`
          : `L${level}${p != null && level < p ? `（前回 L${p} から下がった）` : ""}`;
      all.push({ axis, item, level, prev: p, action: item.actions[0] || "", why });
    }
  }
  // 計測できた項目はレベルが低い順（前回より下がったものを先に）。未計測は「計測できるようにする」を1件だけ混ぜる
  const score = (x: Priority) => (x.level as number) - (x.prev != null && (x.level as number) < x.prev ? 0.5 : 0);
  const measured = all.filter((x) => x.level != null).sort((a, b) => score(a) - score(b));
  const unmeasured = all.filter((x) => x.level == null);
  const picked = measured.slice(0, unmeasured.length ? n - 1 : n);
  if (unmeasured.length) picked.push(unmeasured[0]);
  return picked.slice(0, n);
}

export function goalAt(date: string): MaturityGoal | null {
  const ok = maturityConfig.goals.filter((g) => g.set_on <= date).sort((a, b) => a.set_on.localeCompare(b.set_on));
  return ok[ok.length - 1] ?? maturityConfig.goals[0] ?? null;
}

/** 直近の計測（チーム全体の履歴と、最新日の社員別）。表が無い・空なら空配列 */
export async function loadSnapshots(limit = 26): Promise<{ team: Snapshot[]; employees: Snapshot[]; error?: string }> {
  const sb = createServiceClient();
  if (!sb) return { team: [], employees: [], error: "Supabase 未設定" };
  const { data, error } = await sb
    .from("agent_maturity_snapshots")
    .select("measured_on,scope,metrics")
    .eq("scope", "team")
    .order("measured_on", { ascending: false })
    .limit(limit);
  if (error) return { team: [], employees: [], error: error.message };
  const team = ((data || []) as Snapshot[]).reverse();
  const last = team[team.length - 1];
  if (!last) return { team, employees: [] };
  const emp = await sb
    .from("agent_maturity_snapshots")
    .select("measured_on,scope,metrics")
    .eq("measured_on", last.measured_on)
    .neq("scope", "team")
    .order("scope");
  return { team, employees: (emp.data || []) as Snapshot[] };
}
