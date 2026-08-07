/** Quiet Edge — Health 日次のミニカード＋欠測カバレッジ */

export type VitalDailyRow = {
  recorded_at: string;
  metric: string;
  value: number;
  unit: string | null;
  source: string;
};

const TRACKED = [
  { key: "sleep_hours", label: "睡眠", fmt: (v: number) => `${v.toFixed(1)}時間` },
  { key: "spo2", label: "SpO2", fmt: (v: number) => `${Math.round(v)}%` },
  {
    key: "respiratory_rate",
    label: "呼吸数",
    fmt: (v: number) => `${v.toFixed(1)}回/分`,
  },
  { key: "hrv", label: "HRV", fmt: (v: number) => `${Math.round(v)} ms` },
  {
    key: "resting_hr",
    label: "安静時心拍",
    fmt: (v: number) => `${Math.round(v)} bpm`,
  },
] as const;

function ymdJst(d: Date): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

function addDaysYmd(ymd: string, delta: number): string {
  const [y, m, d] = ymd.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + delta);
  return dt.toISOString().slice(0, 10);
}

export default function QuietEdgeHealthBand({
  rows,
  windowDays = 14,
}: {
  rows: VitalDailyRow[];
  windowDays?: number;
}) {
  const today = ymdJst(new Date());
  const start = addDaysYmd(today, -(windowDays - 1));

  // Prefer oramemo > watch > health_unknown for same day+metric
  const rank = (s: string) =>
    s === "oramemo" ? 0 : s === "watch" ? 1 : 2;

  const best = new Map<string, VitalDailyRow>();
  for (const r of rows) {
    if (r.recorded_at < start || r.recorded_at > today) continue;
    const k = `${r.recorded_at}|${r.metric}`;
    const prev = best.get(k);
    if (!prev || rank(r.source) < rank(prev.source)) best.set(k, r);
  }

  const latestByMetric = new Map<string, VitalDailyRow>();
  for (const r of best.values()) {
    const prev = latestByMetric.get(r.metric);
    if (!prev || r.recorded_at > prev.recorded_at) {
      latestByMetric.set(r.metric, r);
    }
  }

  const days: string[] = [];
  for (let i = 0; i < windowDays; i++) {
    days.push(addDaysYmd(start, i));
  }

  const coverage = TRACKED.map((t) => {
    const present = days.filter((d) => best.has(`${d}|${t.key}`)).length;
    return { ...t, present, total: windowDays };
  });

  const anyData = best.size > 0;

  return (
    <section className="card qe-health-band">
      <header>
        <span className="lvl">Health</span>
        <strong>睡眠・呼吸・心拍（直近）</strong>
      </header>
      {!anyData ? (
        <p className="meta">
          まだ Health 日次がありません。iOSショートカットから ingest するとここに出ます（手順は
          docs/Quiet_Edge_ヘルスケアショートカット手順.md）。
        </p>
      ) : null}

      <div className="qe-health-kpi">
        {TRACKED.map((t) => {
          const row = latestByMetric.get(t.key);
          return (
            <div key={t.key} className="qe-health-kpi-item">
              <p className="meta">{t.label}</p>
              <p className="qe-kpi">
                {row ? t.fmt(Number(row.value)) : "—"}
              </p>
              <p className="meta">
                {row
                  ? `${row.recorded_at} · ${row.source}`
                  : "未取得"}
              </p>
            </div>
          );
        })}
      </div>

      <div className="qe-coverage">
        <p className="meta">
          カバレッジ（直近 {windowDays} 日・欠測可視化）
        </p>
        <ul className="qe-coverage-list">
          {coverage.map((c) => {
            const pct = Math.round((c.present / c.total) * 100);
            return (
              <li key={c.key}>
                <span>
                  {c.label} {c.present}/{c.total}日（{pct}%）
                </span>
                <div className="qe-progress-bar" aria-hidden>
                  <i style={{ width: `${pct}%` }} />
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
