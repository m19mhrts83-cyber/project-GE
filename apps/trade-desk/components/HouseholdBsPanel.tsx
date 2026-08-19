import Link from "next/link";
import type { HouseholdBsRow, HouseholdBsView } from "@/lib/householdBsCompose";
import { fmtYen } from "@/lib/format";

function fmtAmount(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "要確認";
  return fmtYen(n);
}

function rowsFor(rows: HouseholdBsRow[], q: HouseholdBsRow["quadrant"]) {
  return rows.filter((r) => r.quadrant === q);
}

function QuadrantTable({
  title,
  rows,
  totalLabel,
  totalJpy,
}: {
  title: string;
  rows: HouseholdBsRow[];
  totalLabel: string;
  totalJpy: number;
}) {
  return (
    <div className="card" style={{ flex: 1, minWidth: 280 }}>
      <header>
        <span className="lvl">4象限</span>
        <strong>{title}</strong>
      </header>
      {rows.length === 0 ? (
        <p className="meta" style={{ marginTop: 8 }}>
          該当行なし
        </p>
      ) : (
        <table style={{ marginTop: 8 }}>
          <thead>
            <tr>
              <th>項目</th>
              <th className="num">金額</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>
                  {r.label}
                  {r.hint ? (
                    <div className="meta" style={{ fontWeight: 400 }}>
                      {r.hint}
                    </div>
                  ) : null}
                  {r.asOf ? (
                    <div className="meta" style={{ fontWeight: 400 }}>
                      {String(r.asOf).slice(0, 10)}
                      {r.source ? ` · ${r.source}` : ""}
                    </div>
                  ) : null}
                </td>
                <td className="num">{fmtAmount(r.amountJpy)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td>{totalLabel}</td>
              <td className="num">{fmtYen(totalJpy)}</td>
            </tr>
          </tfoot>
        </table>
      )}
    </div>
  );
}

export default function HouseholdBsPanel({ view }: { view: HouseholdBsView }) {
  const { rows, totals, mqSlices, notes } = view;
  const netWorth = totals.assetJpy - totals.liabilityJpy;

  return (
    <div>
      <p className="meta">
        実態（Zaim/MQ/スナップ）が判断の正。キヨサキ4象限は資産と負債の見分け。
        確定申告は{" "}
        <Link href="/tax">/tax</Link>・<Link href="/mq">/mq</Link>{" "}
        の比較物差し（正にしない）。
      </p>

      <div className="mq-dual" style={{ marginTop: 12 }}>
        <QuadrantTable
          title="収入（フロー）"
          rows={rowsFor(rows, "income")}
          totalLabel="収入合計"
          totalJpy={totals.incomeJpy}
        />
        <QuadrantTable
          title="支出（フロー）"
          rows={rowsFor(rows, "expense")}
          totalLabel="支出合計"
          totalJpy={totals.expenseJpy}
        />
      </div>

      <div className="mq-dual" style={{ marginTop: 12 }}>
        <QuadrantTable
          title="資産（ストック）"
          rows={rowsFor(rows, "asset")}
          totalLabel="資産合計"
          totalJpy={totals.assetJpy}
        />
        <QuadrantTable
          title="負債（ストック）"
          rows={rowsFor(rows, "liability")}
          totalLabel="負債合計"
          totalJpy={totals.liabilityJpy}
        />
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">ネット</span>
          <strong>資産 − 負債</strong>
        </header>
        <p style={{ marginTop: 8, fontSize: "1.25rem", fontWeight: 600 }}>
          {fmtYen(netWorth)}
        </p>
      </div>

      <details className="card" style={{ marginTop: 12 }}>
        <summary style={{ cursor: "pointer", fontWeight: 600 }}>
          MQ不動産 · 法人内訳（{view.year}年）
        </summary>
        <table style={{ marginTop: 8 }}>
          <thead>
            <tr>
              <th>主体</th>
              <th className="num">PQ（売上）</th>
              <th className="num">G（利益）</th>
            </tr>
          </thead>
          <tbody>
            {mqSlices.map((s) => (
              <tr key={s.entity}>
                <td>{s.label}</td>
                <td className="num">{fmtAmount(s.pqYen)}</td>
                <td className="num">{fmtAmount(s.gYen)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="meta" style={{ marginTop: 8 }}>
          合算は個人+法人の単純加算。内部取引は除外推奨。
        </p>
      </details>

      {notes.length > 0 ? (
        <ul className="meta" style={{ marginTop: 12 }}>
          {notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
