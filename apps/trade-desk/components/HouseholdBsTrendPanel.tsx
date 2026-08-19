import { fmtYen, fmtYenSigned } from "@/lib/format";
import type { HouseholdBsTrendRow } from "@/lib/householdBsInsights";

function miniAmount(n: number): string {
  const man = Math.round(n / 10_000);
  return `${man.toLocaleString("ja-JP")}万`;
}

function bars(
  rows: HouseholdBsTrendRow[],
  keys: Array<{ key: "incomeJpy" | "expenseJpy" | "cashflowJpy"; label: string; color: string }>
) {
  const max = Math.max(
    1,
    ...rows.flatMap((r) => keys.map((k) => Math.abs(r[k.key] ?? 0)))
  );
  return (
    <div className="lp-year-bars">
      {rows.map((r) => (
        <div key={r.year} className="lp-yb">
          <div className="lp-yb-cols" style={{ gap: 6 }}>
            {keys.map((k) => {
              const v = r[k.key] ?? 0;
              const h = (Math.abs(v) / max) * 100;
              return (
                <div
                  key={k.key}
                  className={`lp-yb-bar${v < 0 ? " neg" : ""}`}
                  style={{ height: `${h}%`, background: k.color }}
                  title={`${r.year}年 ${k.label} ${fmtYen(v)}`}
                />
              );
            })}
          </div>
          <div className="lp-yb-y">{r.year}</div>
        </div>
      ))}
    </div>
  );
}

function lineChart(
  rows: HouseholdBsTrendRow[],
  key: "cashJpy" | "netWorthJpy" | "liabilityJpy",
  color: string,
  ariaLabel: string
) {
  if (rows.length < 2) return <p className="meta">推移データが足りません。</p>;
  const w = 760;
  const h = 220;
  const pad = 24;
  const years = rows.map((r) => r.year);
  const values = rows.map((r) => r[key]);
  const min = Math.min(0, ...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const x0 = years[0];
  const x1 = years[years.length - 1];
  const xspan = x1 - x0 || 1;
  const xy = (year: number, v: number) => {
    const x = pad + ((year - x0) / xspan) * (w - pad * 2);
    const y = h - pad - ((v - min) / span) * (h - pad * 2);
    return { x, y };
  };
  const points = rows.map((r) => {
    const p = xy(r.year, r[key]);
    return `${p.x},${p.y}`;
  });
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      role="img"
      aria-label={ariaLabel}
      style={{ width: "100%", maxWidth: w, height: "auto" }}
    >
      <line
        x1={pad}
        x2={w - pad}
        y1={xy(x0, 0).y}
        y2={xy(x0, 0).y}
        stroke="var(--border, #ccc)"
        strokeWidth={1}
      />
      <polyline fill="none" points={points.join(" ")} stroke={color} strokeWidth={2.6} />
      {rows.map((r) => {
        const p = xy(r.year, r[key]);
        return (
          <g key={`${key}-${r.year}`}>
            <circle cx={p.x} cy={p.y} r={4} fill={color}>
              <title>
                {`${r.year}年 ${fmtYen(r[key])}${r.snapshotAsOf ? ` / snap ${r.snapshotAsOf}` : ""}`}
              </title>
            </circle>
            <text x={p.x - 10} y={h - 8} fontSize={10} fill="var(--muted, #666)">
              {r.year}
            </text>
          </g>
        );
      })}
      <text x={pad} y={14} fontSize={10} fill="var(--muted, #666)">
        {miniAmount(max)}
      </text>
      <text x={pad} y={h - 8} fontSize={10} fill="var(--muted, #666)">
        {miniAmount(min)}
      </text>
    </svg>
  );
}

export default function HouseholdBsTrendPanel({
  rows,
}: {
  rows: HouseholdBsTrendRow[];
}) {
  const sorted = [...rows].sort((a, b) => a.year - b.year);
  const current = sorted[sorted.length - 1] ?? null;
  const prev = sorted.length >= 2 ? sorted[sorted.length - 2] : null;
  return (
    <div style={{ marginTop: 12 }}>
      <div className="card">
        <header>
          <span className="lvl">年次推移</span>
          <strong>キャッシュと純資産の見える化</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          過去推移は年次スナップ基準です。ツールチップで詳細値を確認できます。
          {current && prev
            ? ` 直近は ${current.year}年、前年差は純資産 ${fmtYenSigned(
                current.netWorthJpy - prev.netWorthJpy
              )} / 負債 ${fmtYenSigned(current.liabilityJpy - prev.liabilityJpy)}。`
            : ""}
        </p>
      </div>

      <div className="grid" style={{ marginTop: 12 }}>
        <article className="card">
          <header>
            <span className="lvl">フロー</span>
            <strong>収入・支出・キャッシュ収支</strong>
          </header>
          {bars(sorted, [
            { key: "incomeJpy", label: "収入", color: "#2e7d32" },
            { key: "expenseJpy", label: "支出", color: "#c62828" },
            { key: "cashflowJpy", label: "収支", color: "#1565c0" },
          ])}
        </article>
        <article className="card">
          <header>
            <span className="lvl">現金</span>
            <strong>キャッシュ残高</strong>
          </header>
          {lineChart(sorted, "cashJpy", "#0d47a1", "キャッシュ残高の推移")}
        </article>
        <article className="card">
          <header>
            <span className="lvl">ネット</span>
            <strong>純資産</strong>
          </header>
          {lineChart(sorted, "netWorthJpy", "#2e7d32", "純資産の推移")}
        </article>
        <article className="card">
          <header>
            <span className="lvl">負債</span>
            <strong>負債残高</strong>
          </header>
          {lineChart(sorted, "liabilityJpy", "#8e24aa", "負債残高の推移")}
        </article>
      </div>
    </div>
  );
}
