/** 回復文脈として睡眠・SpO2 の最新値だけ出す */

export type SleepVitalRow = {
  recorded_at: string;
  metric: string;
  value: number;
  source: string;
};

function preferLatest(
  rows: SleepVitalRow[],
  metric: string,
): SleepVitalRow | null {
  const rank = (s: string) =>
    s === "oramemo" ? 0 : s === "watch" ? 1 : 2;
  let best: SleepVitalRow | null = null;
  for (const r of rows) {
    if (r.metric !== metric) continue;
    if (
      !best ||
      r.recorded_at > best.recorded_at ||
      (r.recorded_at === best.recorded_at && rank(r.source) < rank(best.source))
    ) {
      best = r;
    }
  }
  return best;
}

export default function PerformanceSleepStrip({
  rows,
}: {
  rows: SleepVitalRow[];
}) {
  const sleep = preferLatest(rows, "sleep_hours");
  const spo2 = preferLatest(rows, "spo2");

  return (
    <section className="card">
      <header>
        <span className="lvl">回復</span>
        <strong>睡眠・SpO2（参考）</strong>
      </header>
      <p className="meta">
        パフォーマンスの背景としての回復指標。詳細といびき連動は Quiet Edge 側。
      </p>
      <div className="qe-kpi-grid" style={{ marginTop: "0.5rem" }}>
        <article className="card" style={{ margin: 0 }}>
          <p className="meta">睡眠</p>
          <p className="qe-kpi">
            {sleep ? `${Number(sleep.value).toFixed(1)}h` : "—"}
          </p>
          <p className="meta">{sleep?.recorded_at || "未取得"}</p>
        </article>
        <article className="card" style={{ margin: 0 }}>
          <p className="meta">SpO2</p>
          <p className="qe-kpi">
            {spo2 ? `${Math.round(Number(spo2.value))}%` : "—"}
          </p>
          <p className="meta">{spo2?.recorded_at || "未取得"}</p>
        </article>
      </div>
    </section>
  );
}
