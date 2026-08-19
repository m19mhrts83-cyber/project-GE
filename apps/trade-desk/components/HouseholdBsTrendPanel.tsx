import { fmtYen, fmtYenSigned } from "@/lib/format";
import type { HouseholdBsTrendRow } from "@/lib/householdBsInsights";

function miniAmount(n: number): string {
  const man = Math.round(n / 10_000);
  return `${man.toLocaleString("ja-JP")}万`;
}

type LineKey =
  | "incomeJpy"
  | "expenseJpy"
  | "cashExpenseJpy"
  | "cashflowAfterDebtJpy"
  | "cashJpy"
  | "netWorthJpy"
  | "liabilityJpy";

function lineChart(
  rows: HouseholdBsTrendRow[],
  series: Array<{ key: LineKey; label: string; color: string; dash?: boolean }>,
  ariaLabel: string,
  note?: string
) {
  if (rows.length < 2) return <p className="meta">推移データが足りません。</p>;
  const w = 980;
  const h = 280;
  const pad = 42;
  const years = rows.map((r) => r.year);
  const values = rows.flatMap((r) => series.map((s) => r[s.key]));
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
  return (
    <div>
      {note ? (
        <p className="meta" style={{ margin: "0 0 10px" }}>
          {note}
        </p>
      ) : null}
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
        {[max, (max + min) / 2, min].map((tick, idx) => {
          const y = xy(x0, tick).y;
          return (
            <g key={`${tick}-${idx}`}>
              <line
                x1={pad}
                x2={w - pad}
                y1={y}
                y2={y}
                stroke="var(--border, #e4e4e4)"
                strokeWidth={1}
                strokeDasharray="3 4"
              />
              <text x={4} y={y + 4} fontSize={12} fill="var(--muted, #666)">
                {miniAmount(tick)}
              </text>
            </g>
          );
        })}
        {series.map((s) => {
          const points = rows.map((r) => {
            const p = xy(r.year, r[s.key]);
            return `${p.x},${p.y}`;
          });
          return (
            <polyline
              key={s.key}
              fill="none"
              points={points.join(" ")}
              stroke={s.color}
              strokeWidth={3}
              strokeDasharray={s.dash ? "8 6" : undefined}
            />
          );
        })}
        {rows.map((r) => {
          const x = xy(r.year, 0).x;
          return (
            <text
              key={`year-${r.year}`}
              x={x - 12}
              y={h - 10}
              fontSize={12}
              fill="var(--muted, #666)"
            >
              {r.year}
            </text>
          );
        })}
        {series.flatMap((s) =>
          rows.map((r) => {
            const p = xy(r.year, r[s.key]);
            return (
              <circle key={`${s.key}-${r.year}`} cx={p.x} cy={p.y} r={4.5} fill={s.color}>
                <title>
                  {`${r.year}年 ${s.label} ${fmtYen(r[s.key])}${
                    r.snapshotAsOf ? ` / snap ${r.snapshotAsOf}` : ""
                  }`}
                </title>
              </circle>
            );
          })
        )}
      </svg>
      <div
        className="meta"
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "8px 18px",
          marginTop: 10,
        }}
      >
        {series.map((s) => (
          <span key={s.key} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
            <span
              style={{
                width: 18,
                height: 0,
                borderTop: `3px ${s.dash ? "dashed" : "solid"} ${s.color}`,
                display: "inline-block",
              }}
            />
            {s.label}
          </span>
        ))}
      </div>
    </div>
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
          <strong>大きいレンジで見るキャッシュの推移</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          過去推移は年次スナップ基準です。横軸が年、縦軸が金額です。点にカーソルを乗せると各年の金額を確認できます。
          {current && prev
            ? ` 直近は ${current.year}年、前年差は純資産 ${fmtYenSigned(
                current.netWorthJpy - prev.netWorthJpy
              )} / 負債 ${fmtYenSigned(current.liabilityJpy - prev.liabilityJpy)}。`
            : ""}
        </p>
      </div>

      <article className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">フロー</span>
          <strong>収入・返済込みキャッシュ支出・返済後キャッシュ収支</strong>
        </header>
        {lineChart(
          sorted,
          [
            { key: "incomeJpy", label: "収入", color: "#2e7d32" },
            { key: "expenseJpy", label: "会計上の支出", color: "#ef6c00", dash: true },
            { key: "cashExpenseJpy", label: "返済込みキャッシュ支出", color: "#c62828" },
            { key: "cashflowAfterDebtJpy", label: "返済後キャッシュ収支", color: "#1565c0" },
          ],
          "収入と返済込みキャッシュ収支の推移",
          "赤はローン元本返済を含む実際のキャッシュ流出です。青がプラスで積み上がるほど、Cash is King の土台が厚くなります。"
        )}
      </article>

      <article className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">土台</span>
          <strong>キャッシュ残高・純資産・負債残高</strong>
        </header>
        {lineChart(
          sorted,
          [
            { key: "cashJpy", label: "キャッシュ残高", color: "#0d47a1" },
            { key: "netWorthJpy", label: "純資産", color: "#2e7d32" },
            { key: "liabilityJpy", label: "負債残高", color: "#8e24aa" },
          ],
          "キャッシュ残高と純資産の推移",
          "青は手元資金の厚み、緑は積み上がった純資産、紫は負債残高です。純資産が増え、負債が下がり、キャッシュが薄くなりすぎない流れが理想です。"
        )}
      </article>
    </div>
  );
}
