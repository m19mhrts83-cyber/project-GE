import type {
  ReBsColumn,
  ReBusinessPlModel,
  RePlColumn,
  SourcedAmount,
} from "@/lib/reBusinessPlTypes";
import { fmtMqMan } from "@/lib/mqUnits";

function fmtAmt(a: SourcedAmount): string {
  if (a.man == null || !Number.isFinite(a.man)) return "—";
  return fmtMqMan(a.man);
}

function fmtPct(r: number | null): string {
  if (r == null || !Number.isFinite(r)) return "—";
  return `${(r * 100).toFixed(1)}%`;
}

function fmtYears(r: number | null): string {
  if (r == null || !Number.isFinite(r)) return "—";
  return `${r.toFixed(1)}年`;
}

const PL_ROWS: { key: keyof RePlColumn; label: string; bold?: boolean }[] = [
  { key: "rentIncome", label: "不動産収入" },
  { key: "expenseExDep", label: "経費（減価償却除く）", bold: true },
  { key: "expenseManagement", label: "　外注管理費" },
  { key: "expenseTaxPublic", label: "　租税公課" },
  { key: "expenseRepair", label: "　修繕費用" },
  { key: "expenseOther", label: "　他" },
  { key: "depreciation", label: "減価償却費", bold: true },
  { key: "depreciationBuilding", label: "　建物" },
  { key: "depreciationEquipment", label: "　付属設備" },
  { key: "interest", label: "支払利息" },
  { key: "pretaxProfit", label: "税前利益", bold: true },
  { key: "tax", label: "税金" },
  { key: "afterTaxProfit", label: "税後利益", bold: true },
  { key: "taxPaid", label: "税金支払" },
  { key: "principalRepay", label: "元金返済" },
  { key: "cashFlow", label: "キャッシュフロー", bold: true },
];

const BS_ROWS: { key: keyof ReBsColumn; label: string; bold?: boolean }[] = [
  { key: "cash", label: "現預金" },
  { key: "receivables", label: "未収入金" },
  { key: "currentAssets", label: "流動資産", bold: true },
  { key: "building", label: "建物" },
  { key: "equipment", label: "付属設備" },
  { key: "land", label: "土地" },
  { key: "investments", label: "投資" },
  { key: "fixedAssets", label: "固定資産", bold: true },
  { key: "totalAssets", label: "資産合計", bold: true },
  { key: "stLoan", label: "1年内返済" },
  { key: "payables", label: "未払金" },
  { key: "currentLiab", label: "流動負債", bold: true },
  { key: "ltLoan", label: "長期借入金" },
  { key: "deposits", label: "預敷金" },
  { key: "fixedLiab", label: "固定負債", bold: true },
  { key: "totalLiab", label: "負債合計", bold: true },
  { key: "capital", label: "資本金" },
  { key: "retained", label: "利益剰余金" },
  { key: "equity", label: "純資産", bold: true },
  { key: "totalLiabEquity", label: "負債・純資産合計", bold: true },
];

function isSourced(v: unknown): v is SourcedAmount {
  return (
    !!v &&
    typeof v === "object" &&
    "man" in (v as object) &&
    "source" in (v as object)
  );
}

export default function ReBusinessPlPanel({
  model,
}: {
  model: ReBusinessPlModel;
}) {
  const plCols = [...model.columns, model.totalPl];
  const bsCols = [...model.bsColumns, model.totalBs];

  return (
    <div className="re-pl-root" style={{ marginTop: 12 }}>
      <div className="card">
        <header>
          <span className="lvl">事業評価</span>
          <strong>
            不動産事業 BS・PL · {model.year}年（税率{" "}
            {(model.taxRate * 100).toFixed(0)}%）
          </strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          ファイナンス戦略ゼミの行立て。単位は万円。MQ会計・資金繰り・家計BSとは役割が違います。
        </p>
        <ul className="meta" style={{ marginTop: 6, paddingLeft: 18 }}>
          {model.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      </div>

      <div className="card" style={{ marginTop: 12, overflowX: "auto" }}>
        <header>
          <span className="lvl">PL → CF</span>
          <strong>損益とキャッシュフロー橋渡し</strong>
        </header>
        <table className="data" style={{ marginTop: 10, minWidth: 640 }}>
          <thead>
            <tr>
              <th>項目</th>
              {plCols.map((c) => (
                <th key={c.propertyId} style={{ textAlign: "right" }}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {PL_ROWS.map((row) => (
              <tr key={row.key}>
                <td style={row.bold ? { fontWeight: 600 } : undefined}>
                  {row.label}
                </td>
                {plCols.map((c) => {
                  const cell = c[row.key];
                  return (
                    <td
                      key={c.propertyId}
                      style={{
                        textAlign: "right",
                        fontWeight: row.bold ? 600 : undefined,
                      }}
                    >
                      {isSourced(cell) ? fmtAmt(cell) : "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 12, overflowX: "auto" }}>
        <header>
          <span className="lvl">BS</span>
          <strong>貸借対照表（期末・簿価ベース）</strong>
        </header>
        <table className="data" style={{ marginTop: 10, minWidth: 640 }}>
          <thead>
            <tr>
              <th>項目</th>
              {bsCols.map((c) => (
                <th key={c.propertyId} style={{ textAlign: "right" }}>
                  {c.label}
                  {!c.balanced ? (
                    <span className="meta" title="資産と負債・純資産が不一致">
                      {" "}
                      ※
                    </span>
                  ) : null}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {BS_ROWS.map((row) => (
              <tr key={row.key}>
                <td style={row.bold ? { fontWeight: 600 } : undefined}>
                  {row.label}
                </td>
                {bsCols.map((c) => {
                  const cell = c[row.key];
                  return (
                    <td
                      key={c.propertyId}
                      style={{
                        textAlign: "right",
                        fontWeight: row.bold ? 600 : undefined,
                      }}
                    >
                      {isSourced(cell) ? fmtAmt(cell) : "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">指標</span>
          <strong>自己資本比率・流動比率・債務償還・ROI</strong>
        </header>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit,minmax(140px,1fr))",
            gap: 12,
            marginTop: 10,
          }}
        >
          <div>
            <div className="meta">自己資本比率</div>
            <strong>{fmtPct(model.ratios.equityRatio)}</strong>
          </div>
          <div>
            <div className="meta">流動比率</div>
            <strong>{fmtPct(model.ratios.currentRatio)}</strong>
          </div>
          <div>
            <div className="meta">債務償還年数</div>
            <strong>{fmtYears(model.ratios.debtPaybackYears)}</strong>
          </div>
          <div>
            <div className="meta">ROI（CF÷純資産）</div>
            <strong>{fmtPct(model.ratios.roi)}</strong>
          </div>
        </div>
        <p className="meta" style={{ marginTop: 10 }}>
          見方の整理: 事業PLの税後利益と資金繰りCFの差は元本・償却の見え方の差。MQのGは構造評価用でゼミ税前利益の代替ではない。家計BSには事業合計を二重に載せない。
        </p>
      </div>
    </div>
  );
}
