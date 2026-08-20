"use client";

import { useState } from "react";
import OverlayLineChart from "@/components/OverlayLineChart";
import { fmtMqMan, fmtMqManSigned } from "@/lib/mqUnits";
import type { EquityTrendPoint } from "@/lib/mqEquityTrend";
import { equityDelta } from "@/lib/mqEquityTrend";

type Props = {
  title: string;
  points: EquityTrendPoint[];
};

function sourceLabel(s: EquityTrendPoint["source"]): string {
  if (s === "snapshot") return "B/S";
  if (s === "cashflow_project") return "資金繰り投影";
  return "なし";
}

export default function MqEquityTrendPanel({ title, points }: Props) {
  const years = points.map((p) => p.year);
  const equity = points.map((p) => p.equityMan);
  const capital = points.map((p) => p.capitalMan);
  const retained = points.map((p) => p.retainedMan);
  const profit = points.map((p) => p.profitMan);
  const known = points.filter((p) => p.equityMan != null);
  const delta = equityDelta(points);
  const [showParts, setShowParts] = useState(false);

  const series = [
    { key: "equity", label: "自己資本", values: equity, emphasis: true },
    ...(showParts
      ? [
          { key: "capital", label: "資本金等", values: capital },
          { key: "retained", label: "繰越利益", values: retained },
          { key: "profit", label: "当期利益", values: profit },
        ]
      : []),
  ];

  return (
    <div className="card mq-equity-trend-card">
      <header>
        <span className="lvl">推移</span>
        <strong>{title}</strong>
      </header>
      <p className="meta" style={{ marginTop: 8 }}>
        自己資本 = 資本金等 + 繰越利益 + 当期利益（万円）。毎期末（12/31 に最も近い B/S）をプロットします。
        スナップが無い年は資金繰り投影を使います。
      </p>
      {known.length === 0 ? (
        <p className="meta" style={{ marginTop: 10 }}>
          まだプロットできる期末がありません。軽量B/Sを保存するか、整合レーンから資金繰りを反映するとここに出ます。
        </p>
      ) : (
        <>
          <p className="meta" style={{ marginTop: 8 }}>
            {known.length}期末
            {delta != null ? ` · 初期末→最新 ${fmtMqManSigned(delta)}` : ""}
          </p>
          <label className="mq-cashflow-reclassify-learn" style={{ marginTop: 8 }}>
            <input
              type="checkbox"
              checked={showParts}
              onChange={(e) => setShowParts(e.target.checked)}
            />
            内訳（資本金・繰越・当期利益）も重ねる
          </label>
          <div style={{ marginTop: 12 }}>
            <OverlayLineChart
              years={years}
              series={series}
              ariaLabel="自己資本の年次推移"
              formatValue={(v) => fmtMqMan(v)}
              allowSinglePoint
            />
          </div>
          <div className="mq-cashflow-scroll" style={{ marginTop: 12 }}>
            <table className="mq-table">
              <thead>
                <tr>
                  <th>期末</th>
                  <th>基準日</th>
                  <th>出典</th>
                  <th className="num">資本金等</th>
                  <th className="num">繰越利益</th>
                  <th className="num">当期利益</th>
                  <th className="num">自己資本</th>
                </tr>
              </thead>
              <tbody>
                {points.map((p) => (
                  <tr key={p.year}>
                    <td>{p.year}年</td>
                    <td>{p.asOf ?? "—"}</td>
                    <td>
                      {sourceLabel(p.source)}
                      {p.note ? ` · ${p.note}` : ""}
                    </td>
                    <td className="num">{fmtMqMan(p.capitalMan)}</td>
                    <td className="num">{fmtMqMan(p.retainedMan)}</td>
                    <td className="num">{fmtMqMan(p.profitMan)}</td>
                    <td className="num">
                      <strong>{fmtMqMan(p.equityMan)}</strong>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
