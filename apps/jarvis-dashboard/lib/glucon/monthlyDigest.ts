/** グルコン期間の metrics / 入退去イベント集約 */

import sources from "@/data/glucon_sources.json";
import { createClient } from "@/lib/supabase/server";
import {
  digestYoritooriRange,
  formatYoritooriDigestText,
  type YoritooriDigestLine,
  type YoritooriDigestResult,
} from "./yoritooriDigest";

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
): Promise<OccupancyDigestEvent[]> {
  const supabase = await createClient();
  const { data } = await supabase
    .from("property_occupancy_events")
    .select(
      "occurred_on,event_type,property_name,property_id,room,note",
    )
    .gte("occurred_on", from)
    .lte("occurred_on", to)
    .order("occurred_on", { ascending: true })
    .limit(100);
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
  notices: string[];
}): string {
  const notice =
    args.notices.length > 0
      ? `\n【集約メモ】\n${args.notices.map((n) => `- ${n}`).join("\n")}`
      : "";
  return `【今月の動き（メール・数値・入退去）】期間 ${args.from} 〜 ${args.to}
※ Journal と並列の事実ソース。ここに無い成果・金額を捏造しない。

〈パートナーやり取り（不動産関連）〉
${args.yoritooriText}

〈モチベーション数値（metrics）〉
${args.metricsText}

〈入居・空室イベント〉
${args.occupancyText}
${notice}
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

  const yoritooriText = formatYoritooriDigestText(yoritoori);
  const metricsText = formatMetricsText(metricsRows);
  const occupancyText = formatOccupancyText(occupancyEvents);
  const notices = [...yoritoori.notices];

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
    occupancy: { events: occupancyEvents, text: occupancyText },
    promptBlock: buildPromptBlock({
      from,
      to,
      yoritooriText,
      metricsText,
      occupancyText,
      notices,
    }),
  };
}
