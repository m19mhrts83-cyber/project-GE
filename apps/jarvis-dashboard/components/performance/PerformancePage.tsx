import Shell from "@/components/Shell";
import PerformanceJournalBand from "@/components/performance/PerformanceJournalBand";
import PerformanceSleepStrip from "@/components/performance/PerformanceSleepStrip";
import {
  filterJournalByLens,
  LENS_META,
  type PerformanceJournalRow,
  type PerformanceLens,
} from "@/lib/performance";
import { createClient } from "@/lib/supabase/server";

function addDaysYmd(ymd: string, delta: number): string {
  const [y, m, d] = ymd.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + delta);
  return dt.toISOString().slice(0, 10);
}

function ymdJst(d = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

async function loadPerformanceState(lens: PerformanceLens) {
  const supabase = await createClient();
  const today = ymdJst();
  const since = addDaysYmd(today, -29);

  const [{ data: journals }, { data: vitals }] = await Promise.all([
    supabase
      .from("vital_journal_daily")
      .select("recorded_at, excerpt, char_count, sleep_signal, sleep_tags")
      .gte("recorded_at", since)
      .order("recorded_at", { ascending: false }),
    supabase
      .from("vital_daily")
      .select("recorded_at, metric, value, source")
      .in("metric", ["sleep_hours", "spo2"])
      .gte("recorded_at", since)
      .order("recorded_at", { ascending: false }),
  ]);

  const filtered = filterJournalByLens(
    (journals || []) as PerformanceJournalRow[],
    lens,
  );

  return {
    rows: filtered.slice(0, 20),
    vitals: (vitals || []).map((v) => ({
      recorded_at: String(v.recorded_at),
      metric: String(v.metric),
      value: Number(v.value),
      source: String(v.source || "health_unknown"),
    })),
  };
}

export async function PerformancePage({ lens }: { lens: PerformanceLens }) {
  const meta = LENS_META[lens];
  const state = await loadPerformanceState(lens);
  const href =
    lens === "work" ? "/performance/work" : "/performance/move";

  return (
    <Shell active={href}>
      <h1>{meta.title}</h1>
      <p className="sub">{meta.subtitle}</p>
      <PerformanceSleepStrip rows={state.vitals} />
      <PerformanceJournalBand lens={lens} rows={state.rows} />
    </Shell>
  );
}
