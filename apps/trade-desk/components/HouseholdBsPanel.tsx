import Link from "next/link";
import type { HouseholdBsRow, HouseholdBsView } from "@/lib/householdBsCompose";
import { fmtManRounded } from "@/lib/format";

function fmtAmount(n: number | null | undefined): string {
  return fmtManRounded(n);
}

function rowsFor(rows: HouseholdBsRow[], q: HouseholdBsRow["quadrant"]) {
  return rows.filter((r) => r.quadrant === q && r.countsTowardTotal);
}

function detailRowsFor(rows: HouseholdBsRow[], q: HouseholdBsRow["quadrant"]) {
  return rows.filter(
    (r) =>
      r.quadrant === q &&
      (r.countsTowardTotal || r.indent || r.amountJpy != null)
  );
}

function RowMeta({ r }: { r: HouseholdBsRow }) {
  return (
    <>
      {r.hint ? (
        <div className="meta" style={{ fontWeight: 400 }}>
          {r.hint}
        </div>
      ) : null}
      {r.asOf ? (
        <div className="meta" style={{ fontWeight: 400 }}>
          {String(r.asOf).slice(0, 10)}
          {r.source ? ` · ${r.source}` : ""}
          {r.staleDays != null && r.staleDays > 14
            ? ` · ⚠ ${r.staleDays}日前`
            : r.staleDays != null
              ? ` · ${r.staleDays}日前`
              : ""}
        </div>
      ) : null}
    </>
  );
}

function BreakdownTable({ rows }: { rows: HouseholdBsRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="meta" style={{ marginTop: 8 }}>
        該当行なし
      </p>
    );
  }
  return (
    <table style={{ marginTop: 8 }}>
      <thead>
        <tr>
          <th>項目</th>
          <th className="num">金額（万円）</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id}>
            <td>
              {r.label}
              <RowMeta r={r} />
            </td>
            <td className="num">{fmtAmount(r.amountJpy)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function FlowQuadrantCard({
  title,
  quadrant,
  rows,
  allRows,
  totalLabel,
  totalJpy,
}: {
  title: string;
  quadrant: HouseholdBsRow["quadrant"];
  rows: HouseholdBsRow[];
  allRows: HouseholdBsRow[];
  totalLabel: string;
  totalJpy: number;
}) {
  const breakdown = detailRowsFor(allRows, quadrant);
  const count = breakdown.filter((r) => r.countsTowardTotal).length;

  return (
    <div className="card bs-quadrant" style={{ flex: 1, minWidth: 280 }}>
      <header>
        <span className="lvl">4象限</span>
        <strong>{title}</strong>
      </header>
      <div className="bs-quadrant-total">
        <span className="bs-quadrant-total-label">{totalLabel}</span>
        <span className="bs-quadrant-total-value">{fmtAmount(totalJpy)}</span>
      </div>
      <details className="bs-breakdown" open={count > 0 && count <= 8}>
        <summary>
          内訳
          {count > 0 ? `（${count}件）` : ""}
        </summary>
        <BreakdownTable rows={breakdown} />
      </details>
    </div>
  );
}

function StockQuadrantCard({
  title,
  quadrant,
  rows,
  allRows,
  totalLabel,
  totalJpy,
}: {
  title: string;
  quadrant: HouseholdBsRow["quadrant"];
  rows: HouseholdBsRow[];
  allRows: HouseholdBsRow[];
  totalLabel: string;
  totalJpy: number;
}) {
  const breakdown = detailRowsFor(allRows, quadrant);

  return (
    <div className="card bs-quadrant" style={{ flex: 1, minWidth: 280 }}>
      <header>
        <span className="lvl">4象限</span>
        <strong>{title}</strong>
      </header>
      <div className="bs-quadrant-total">
        <span className="bs-quadrant-total-label">{totalLabel}</span>
        <span className="bs-quadrant-total-value">{fmtAmount(totalJpy)}</span>
      </div>
      <BreakdownTable rows={breakdown} />
    </div>
  );
}

export default function HouseholdBsPanel({ view }: { view: HouseholdBsView }) {
  const { rows, totals, mqSlices, notes } = view;
  const netWorth = totals.assetJpy - totals.liabilityJpy;
  const incomeRows = rowsFor(rows, "income");
  const expenseRows = rowsFor(rows, "expense");
  const assetRows = rowsFor(rows, "asset");
  const liabilityRows = rowsFor(rows, "liability");

  return (
    <div>
      <p className="meta">
        金額は<strong>万円単位（四捨五入）</strong>。実態（Zaim/MQ/ローントラッカー）が判断の正。
        確定申告は <Link href="/tax">/tax</Link>・<Link href="/mq">/mq</Link>{" "}
        の比較物差し（正にしない）。
      </p>

      <div className="mq-dual" style={{ marginTop: 12 }}>
        <FlowQuadrantCard
          title="収入（フロー）"
          quadrant="income"
          rows={incomeRows}
          allRows={rows}
          totalLabel="収入合計"
          totalJpy={totals.incomeJpy}
        />
        <FlowQuadrantCard
          title="支出（フロー）"
          quadrant="expense"
          rows={expenseRows}
          allRows={rows}
          totalLabel="支出合計（返済込み）"
          totalJpy={totals.expenseJpy}
        />
      </div>

      <div className="mq-dual" style={{ marginTop: 12 }}>
        <StockQuadrantCard
          title="資産（左・買ったもの）"
          quadrant="asset"
          rows={assetRows}
          allRows={rows}
          totalLabel="資産合計"
          totalJpy={totals.assetJpy}
        />
        <StockQuadrantCard
          title="負債（右・借りたお金）"
          quadrant="liability"
          rows={liabilityRows}
          allRows={rows}
          totalLabel="負債合計"
          totalJpy={totals.liabilityJpy}
        />
      </div>
      <p className="meta" style={{ marginTop: 6 }}>
        会計のB/Sと同じ向きです。左が資産、右が負債。自己資本（純資産）は下の「資産 − 負債」。
        キヨサキ4象限の上段（収入/支出）は損益計算書側で、B/Sの右側ではありません。
      </p>
      <p className="meta" style={{ marginTop: 6 }}>
        この画面の支出合計は Cash is King を優先し、ローン元本返済を含むキャッシュ支出で表示します。
        会計上の支出との差は、上部サマリーと年次グラフで分けて確認できます。
      </p>

      <div className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">ネット</span>
          <strong>資産 − 負債</strong>
        </header>
        <p className="bs-quadrant-total-value" style={{ marginTop: 8 }}>
          {fmtAmount(netWorth)}
        </p>
      </div>

      <details className="card" style={{ marginTop: 12 }} open>
        <summary style={{ cursor: "pointer", fontWeight: 600 }}>
          不動産の内訳
        </summary>
        {view.filedRe?.useFiledInTotals ? (
          <p className="meta" style={{ marginTop: 8 }}>
            この年は確定申告の収入金額が正（個人 {fmtAmount(view.filedRe.personalRevenueJpy)}
            {view.filedRe.corporateRevenueJpy
              ? ` ／ 法人5月期 ${fmtAmount(view.filedRe.corporateRevenueJpy)}`
              : ""}
            ）。内容確認は参考。
            {view.filedRe.personalSource ? (
              <>
                {" "}
                PDF: <code>{view.filedRe.personalSource}</code>
              </>
            ) : null}
          </p>
        ) : (
          <p className="meta" style={{ marginTop: 8 }}>
            未申告年は内容確認×所有月。申告後に PDF を正へ差し替えます。
          </p>
        )}
        {view.reFlow && view.reFlow.properties.length > 0 ? (
          <>
            <p className="meta" style={{ marginTop: 8 }}>
              {view.reFlow.basis}（基準日 {view.reFlow.asOf}）
            </p>
            <table style={{ marginTop: 8 }}>
              <thead>
                <tr>
                  <th>物件</th>
                  <th>月数</th>
                  <th className="num">家賃</th>
                  <th className="num">管理費</th>
                  <th className="num">グロス</th>
                </tr>
              </thead>
              <tbody>
                {view.reFlow.properties.map((p) => (
                  <tr key={p.id}>
                    <td>
                      {p.label}
                      <div className="meta">{p.owner}</div>
                    </td>
                    <td>{p.months}</td>
                    <td className="num">{fmtAmount(p.rentJpy)}</td>
                    <td className="num">{fmtAmount(p.mgmtJpy)}</td>
                    <td className="num">{fmtAmount(p.grossJpy)}</td>
                  </tr>
                ))}
                <tr>
                  <td colSpan={2}>
                    <strong>合計</strong>
                  </td>
                  <td className="num">
                    {fmtAmount(view.reFlow.totals.rentJpy)}
                  </td>
                  <td className="num">
                    {fmtAmount(view.reFlow.totals.mgmtJpy)}
                  </td>
                  <td className="num">
                    {fmtAmount(view.reFlow.totals.grossJpy)}
                  </td>
                </tr>
              </tbody>
            </table>
            <p className="meta" style={{ marginTop: 8 }}>
              準拠: <code>docs/KURASHIFT_家計BS_不動産フロー.md</code> ／{" "}
              <code>config/household_kiyosaki_bs.yaml</code> の{" "}
              <code>realestate_flow</code>
            </p>
          </>
        ) : (
          <p className="meta" style={{ marginTop: 8 }}>
            この年の所有月が無い、または号室データがありません。
          </p>
        )}
      </details>

      <details className="card" style={{ marginTop: 12 }}>
        <summary style={{ cursor: "pointer", fontWeight: 600 }}>
          MQ不動産 · 法人内訳（{view.year}年・参考）
        </summary>
        <table style={{ marginTop: 8 }}>
          <thead>
            <tr>
              <th>主体</th>
              <th className="num">PQ（万円）</th>
              <th className="num">G（万円）</th>
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
          合算は個人+法人の単純加算。家計B/Sの収入・支出合計には入れていません（内容確認が正）。
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
