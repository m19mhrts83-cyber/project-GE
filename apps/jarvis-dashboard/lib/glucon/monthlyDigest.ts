/** グルコン期間の metrics / 入退去イベント集約 */

import sources from "@/data/glucon_sources.json";
import { createClient } from "@/lib/supabase/server";
import type { EarlyFillHint } from "./types";
import {
  digestYoritooriRange,
  formatYoritooriDigestText,
  type YoritooriDigestLine,
  type YoritooriDigestResult,
} from "./yoritooriDigest";

export type { EarlyFillHint };

export type MetricsDigestRow = {
  recorded_at: string;
  metric: string;
  entity: string;
  value: number;
  unit: string | null;
};

export type OccupancyDigestEvent = {
  occurred_on: string;
  event_type: "vacant" | "occupied" | string;
  property_name: string;
  room: string;
  note: string | null;
};

/** 退去→入居がこの日数以下なら「早期」 */
export const EARLY_FILL_DAYS = 30;

export type GluconMonthlyDigest = {
  from: string;
  to: string;
  yoritoori: {
    lines: YoritooriDigestLine[];
    text: string;
    notices: string[];
    skipped: string[];
    ok: boolean;
  };
  metrics: {
    rows: MetricsDigestRow[];
    text: string;
  };
  occupancy: {
    events: OccupancyDigestEvent[];
    text: string;
    earlyFills: EarlyFillHint[];
    earlyFillText: string;
  };
  promptBlock: string;
};

const DEFAULT_METRICS = [
  "cashflow",
  "rent_income",
  "expense_total",
  "repair_expense",
  "income_total",
  "energy_net_cf",
];

function metricList(): string[] {
  const raw = (sources as { metrics?: string[] }).metrics;
  return Array.isArray(raw) && raw.length ? raw : DEFAULT_METRICS;
}

function fmtYen(n: number): string {
  return `${Math.round(n).toLocaleString("ja-JP")}円`;
}

function formatMetricsText(rows: MetricsDigestRow[]): string {
  if (!rows.length) return "（期間内の metrics なし）";
  // recorded_at は月次（YYYY-MM-01）想定。entity×metric の期間内最新と前値
  const byKey = new Map<string, MetricsDigestRow[]>();
  for (const r of rows) {
    const k = `${r.entity}|${r.metric}`;
    const arr = byKey.get(k) || [];
    arr.push(r);
    byKey.set(k, arr);
  }
  const lines: string[] = [];
  for (const [k, arr] of [...byKey.entries()].sort()) {
    const sorted = [...arr].sort((a, b) =>
      a.recorded_at.localeCompare(b.recorded_at),
    );
    const last = sorted[sorted.length - 1];
    const prev = sorted.length > 1 ? sorted[sorted.length - 2] : null;
    const [entity, metric] = k.split("|");
    const unit = last.unit || "";
    const cur =
      unit === "円" || !unit
        ? fmtYen(last.value)
        : `${last.value}${unit}`;
    let delta = "";
    if (prev) {
      const d = last.value - prev.value;
      const ds =
        unit === "円" || !unit
          ? fmtYen(d)
          : `${d > 0 ? "+" : ""}${d}${unit}`;
      delta = `（前月差 ${d > 0 ? "+" : ""}${ds}）`;
    }
    lines.push(
      `- ${last.recorded_at.slice(0, 7)} ${entity}/${metric}: ${cur}${delta}`,
    );
  }
  return lines.join("\n");
}

function formatOccupancyText(events: OccupancyDigestEvent[]): string {
  if (!events.length) return "（期間内の入居・空室イベントなし）";
  return events
    .map((e) => {
      const kind = e.event_type === "vacant" ? "空室" : "入居";
      const note = e.note ? ` — ${e.note}` : "";
      return `- ${e.occurred_on} ${e.property_name} ${e.room} ${kind}${note}`;
    })
    .join("\n");
}

function daysBetween(a: string, b: string): number {
  const ta = Date.parse(`${a}T00:00:00+09:00`);
  const tb = Date.parse(`${b}T00:00:00+09:00`);
  if (!Number.isFinite(ta) || !Number.isFinite(tb)) return -1;
  return Math.round((tb - ta) / 86400000);
}

function unitKey(property: string, room: string): string {
  return `${property.trim()}|${room.trim()}`;
}

/** 期間内の入居に対し、直近の空室日からの日数を計算 */
export function computeEarlyFills(
  events: OccupancyDigestEvent[],
  periodFrom: string,
  periodTo: string,
  earlyDays = EARLY_FILL_DAYS,
): EarlyFillHint[] {
  const sorted = [...events].sort((a, b) =>
    a.occurred_on.localeCompare(b.occurred_on),
  );
  const lastVacant = new Map<string, string>();
  const out: EarlyFillHint[] = [];

  for (const e of sorted) {
    const key = unitKey(e.property_name, e.room);
    if (e.event_type === "vacant") {
      lastVacant.set(key, e.occurred_on);
      continue;
    }
    if (e.event_type !== "occupied") continue;
    if (e.occurred_on < periodFrom || e.occurred_on > periodTo) continue;
    const vacantOn = lastVacant.get(key);
    if (!vacantOn) continue;
    const days = daysBetween(vacantOn, e.occurred_on);
    if (days < 0) continue;
    out.push({
      property_name: e.property_name,
      room: e.room,
      vacant_on: vacantOn,
      occupied_on: e.occurred_on,
      days,
      early: days <= earlyDays,
    });
  }
  return out;
}

export function formatEarlyFillText(fills: EarlyFillHint[]): string {
  if (!fills.length) return "";
  const lines = fills.map((f) => {
    const tag = f.early ? "早期" : "通常";
    return `- ${f.property_name} ${f.room}: 退去 ${f.vacant_on} → 入居 ${f.occupied_on}（${f.days}日・${tag}）`;
  });
  return `〈空室→入居の日数（成果候補）〉\n${lines.join("\n")}`;
}

async function loadMetricsRange(
  from: string,
  to: string,
): Promise<MetricsDigestRow[]> {
  const supabase = await createClient();
  const metrics = metricList();
  const { data } = await supabase
    .from("metrics")
    .select("recorded_at,metric,entity,value,unit")
    .in("metric", metrics)
    .gte("recorded_at", from)
    .lte("recorded_at", to)
    .order("recorded_at", { ascending: true })
    .limit(400);
  return (data || []).map((r) => ({
    recorded_at: String(r.recorded_at),
    metric: String(r.metric),
    entity: String(r.entity || "all"),
    value: Number(r.value),
    unit: r.unit ? String(r.unit) : null,
  }));
}

async function loadOccupancyRange(
  from: string,
  to: string,
  lookbackDays = 120,
): Promise<OccupancyDigestEvent[]> {
  const supabase = await createClient();
  // 早期入居計算のため、期間前の空室イベントも取得
  const lookbackFrom = (() => {
    const t = Date.parse(`${from}T00:00:00+09:00`);
    if (!Number.isFinite(t)) return from;
    const d = new Date(t - lookbackDays * 86400000);
    return d.toISOString().slice(0, 10);
  })();
  const { data } = await supabase
    .from("property_occupancy_events")
    .select(
      "occurred_on,event_type,property_name,property_id,room,note",
    )
    .gte("occurred_on", lookbackFrom)
    .lte("occurred_on", to)
    .order("occurred_on", { ascending: true })
    .limit(200);
  return (data || []).map((r) => ({
    occurred_on: String(r.occurred_on),
    event_type: String(r.event_type),
    property_name: String(r.property_name || r.property_id || "物件"),
    room: String(r.room || ""),
    note: r.note ? String(r.note) : null,
  }));
}

function buildPromptBlock(args: {
  from: string;
  to: string;
  yoritooriText: string;
  metricsText: string;
  occupancyText: string;
  earlyFillText?: string;
  notices: string[];
}): string {
  const notice =
    args.notices.length > 0
      ? `\n【集約メモ】\n${args.notices.map((n) => `- ${n}`).join("\n")}`
      : "";
  const early = args.earlyFillText?.trim()
    ? `\n${args.earlyFillText.trim()}\n`
    : "";
  return `【今月の動き（メール・数値・入退去）】期間 ${args.from} 〜 ${args.to}
※ Journal と並列の事実ソース。ここに無い成果・金額を捏造しない。

〈パートナーやり取り（不動産関連）〉
${args.yoritooriText}

〈モチベーション数値（metrics）〉
${args.metricsText}

〈入居・空室イベント〉
${args.occupancyText}
${early}${notice}
`;
}

export async function buildGluconMonthlyDigest(
  from: string,
  to: string,
): Promise<GluconMonthlyDigest> {
  let yoritoori: YoritooriDigestResult = {
    ok: false,
    from,
    to,
    lines: [],
    notices: [],
    skipped: [],
  };
  try {
    yoritoori = await digestYoritooriRange(from, to);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    yoritoori = {
      ok: false,
      from,
      to,
      lines: [],
      notices: [`やり取り集約失敗: ${msg}`.slice(0, 160)],
      skipped: [],
    };
  }

  let metricsRows: MetricsDigestRow[] = [];
  try {
    metricsRows = await loadMetricsRange(from, to);
  } catch {
    metricsRows = [];
  }

  let occupancyEvents: OccupancyDigestEvent[] = [];
  try {
    occupancyEvents = await loadOccupancyRange(from, to);
  } catch {
    occupancyEvents = [];
  }

  const periodEvents = occupancyEvents.filter(
    (e) => e.occurred_on >= from && e.occurred_on <= to,
  );
  const earlyFills = computeEarlyFills(occupancyEvents, from, to);
  const yoritooriText = formatYoritooriDigestText(yoritoori);
  const metricsText = formatMetricsText(metricsRows);
  const occupancyText = formatOccupancyText(periodEvents);
  const earlyFillText = formatEarlyFillText(earlyFills);
  const notices = [...yoritoori.notices];
  if (earlyFills.some((f) => f.early)) {
    notices.push(
      `早期入居候補 ${earlyFills.filter((f) => f.early).length} 件（退去から${EARLY_FILL_DAYS}日以内）`,
    );
  }

  return {
    from,
    to,
    yoritoori: {
      lines: yoritoori.lines,
      text: yoritooriText,
      notices: yoritoori.notices,
      skipped: yoritoori.skipped,
      ok: yoritoori.ok,
    },
    metrics: { rows: metricsRows, text: metricsText },
    occupancy: {
      events: periodEvents,
      text: occupancyText,
      earlyFills,
      earlyFillText,
    },
    promptBlock: buildPromptBlock({
      from,
      to,
      yoritooriText,
      metricsText,
      occupancyText,
      earlyFillText,
      notices,
    }),
  };
}
