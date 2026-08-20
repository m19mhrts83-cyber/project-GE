"use client";

export default function MqMetricsTrendPlaceholder() {
  return (
    <div className="card" style={{ marginTop: 12 }}>
      <header>
        <span className="lvl">準備中</span>
        <strong>MQ指標の年次横並び</strong>
      </header>
      <p className="meta" style={{ marginTop: 8 }}>
        次に、PQ / VQ / F / G / m/p を年で横並びにして「年々良くなっているか」を見られる表を置きます。
        いまは自己資本グラフを先に使ってください。
      </p>
      <table className="mq-table" style={{ marginTop: 10, opacity: 0.55 }}>
        <thead>
          <tr>
            <th>指標</th>
            <th className="num">2025</th>
            <th className="num">2026</th>
            <th>評価</th>
          </tr>
        </thead>
        <tbody>
          {["PQ 売上", "VQ 変動費", "F 固定費", "G 利益", "m/p"].map((k) => (
            <tr key={k}>
              <td>{k}</td>
              <td className="num">—</td>
              <td className="num">—</td>
              <td className="meta">（次フェーズ）</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
