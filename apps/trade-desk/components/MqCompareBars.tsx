import { fmtYen } from "@/lib/format";

type BarRow = { label: string; value: number };

export default function MqCompareBars({
  titleA,
  titleB,
  rowsA,
  rowsB,
}: {
  titleA: string;
  titleB: string;
  rowsA: BarRow[];
  rowsB: BarRow[];
}) {
  const max = Math.max(
    1,
    ...rowsA.map((r) => Math.abs(r.value)),
    ...rowsB.map((r) => Math.abs(r.value))
  );

  function Col({ title, rows }: { title: string; rows: BarRow[] }) {
    return (
      <div className="mq-compare-col">
        <div className="meta" style={{ fontWeight: 600, marginBottom: 8 }}>
          {title}
        </div>
        {rows.length === 0 ? (
          <p className="meta">データなし</p>
        ) : (
          rows.map((r) => (
            <div key={r.label} className="mq-bar-row">
              <div className="mq-bar-label">{r.label}</div>
              <div className="mq-bar-track">
                <div
                  className="mq-bar-fill"
                  style={{
                    width: `${Math.min(100, (Math.abs(r.value) / max) * 100)}%`,
                  }}
                />
              </div>
              <div className="num mq-bar-val">{fmtYen(Math.round(r.value))}</div>
            </div>
          ))
        )}
      </div>
    );
  }

  const labels = Array.from(
    new Set([...rowsA.map((r) => r.label), ...rowsB.map((r) => r.label)])
  );
  const deltaRows = labels.map((label) => {
    const a = rowsA.find((r) => r.label === label)?.value ?? 0;
    const b = rowsB.find((r) => r.label === label)?.value ?? 0;
    return { label, value: a - b };
  });

  return (
    <div className="card">
      <header>
        <span className="lvl">2時点比較</span>
        <strong>左右の期間を独立選択</strong>
      </header>
      <div className="mq-compare-grid" style={{ marginTop: 12 }}>
        <Col title={titleA} rows={rowsA} />
        <Col title={titleB} rows={rowsB} />
      </div>
      {deltaRows.some((r) => r.value !== 0) ? (
        <div style={{ marginTop: 16 }}>
          <div className="meta" style={{ fontWeight: 600 }}>
            差分（左 − 右）
          </div>
          <table style={{ marginTop: 6 }}>
            <tbody>
              {deltaRows.map((r) => (
                <tr key={r.label}>
                  <td>{r.label}</td>
                  <td className="num">{fmtYen(Math.round(r.value))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
