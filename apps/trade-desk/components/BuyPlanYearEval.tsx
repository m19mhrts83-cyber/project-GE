"use client";

import OverlayLineChart, {
  type OverlaySeries,
} from "@/components/OverlayLineChart";
import { fmtYen } from "@/lib/format";
import { CF_CHART_GOAL_YEN } from "@/lib/buyPlanCfSeries";

export type YearEvalRow = {
  year: number;
  planLatestYen: number | null;
  opsYen: number | null;
  specialYtd: number;
};

export default function BuyPlanYearEval({
  years,
  series,
  rows,
  markers,
}: {
  years: number[];
  series: OverlaySeries[];
  rows: YearEvalRow[];
  markers: { year: number; label: string }[];
}) {
  const latestKey = series.find((s) => s.emphasis)?.key;
  return (
    <div className="card">
      <header>
        <span className="lvl">年度評価</span>
        <strong>想定 vs 実績 · キャッシュフロー推移</strong>
      </header>
      <p className="meta" style={{ marginTop: 6 }}>
        計画線＝買い進め Excel メジャー版ごとの想定月次CF（粗＝利回り×価格、返済控除なし）。
        実際のキャッシュフロー＝Zaim 定常（家賃−ローン−毎月経費）。版が新しくなるほど「実績を踏まえた想定の更新」として読む。
      </p>
      <div style={{ marginTop: 12 }}>
        <OverlayLineChart
          years={years}
          series={series}
          goalYen={CF_CHART_GOAL_YEN}
          markers={markers}
          ariaLabel="計画版と実際のキャッシュフロー推移"
        />
      </div>
      <h2 style={{ fontSize: 15, margin: "16px 0 8px" }}>年度ごとの評価</h2>
      <table>
        <thead>
          <tr>
            <th>年</th>
            <th className="num">計画（最新版）</th>
            <th className="num">実際のCF（定常）</th>
            <th className="num">差（実−計）</th>
            <th className="num">特別支出（年）</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const diff =
              r.planLatestYen != null && r.opsYen != null
                ? r.opsYen - r.planLatestYen
                : null;
            return (
              <tr key={r.year}>
                <td>{r.year}</td>
                <td className="num">
                  {r.planLatestYen != null ? fmtYen(r.planLatestYen) : "—"}
                </td>
                <td className="num">
                  {r.opsYen != null ? fmtYen(r.opsYen) : "—"}
                </td>
                <td className="num meta">
                  {diff != null
                    ? `${diff >= 0 ? "+" : ""}${fmtYen(diff)}`
                    : "—"}
                </td>
                <td className="num meta">
                  {r.specialYtd ? fmtYen(r.specialYtd) : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {latestKey ? (
        <p className="meta" style={{ marginTop: 8 }}>
          表の「計画（最新版）」は強調中の計画線（{latestKey}）の年末値。
        </p>
      ) : null}
    </div>
  );
}
