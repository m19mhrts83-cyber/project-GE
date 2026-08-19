import type { MqCashflowMonthRow } from "@/lib/mqCashflow";
import { fmtMqMan } from "@/lib/mqUnits";

type Props = {
  title: string;
  year: string; // 表示用
  rows: MqCashflowMonthRow[];
  grainHint?: string; // 例: "年次の選択年（各月）"
  unavailableReason?: string | null;
};

type RowKey =
  | "salesMan"
  | "repairMan"
  | "advertisingMan"
  | "expenseMan"
  | "managementMan"
  | "acquisitionMan"
  | "taxAccountantMan"
  | "loanRepaymentMan"
  | "annualTaxMan"
  | "cashEndMan"
  | "netCashFlowMan"
  | "repaymentRatio";

type RowSection = "income" | "expense" | "summary" | "metric";

const ROWS: Array<{
  key: RowKey;
  section: RowSection;
  sectionLabel: string;
  shortLabel: string;
  note: string;
  kind: "money" | "ratio";
}> = [
  {
    key: "salesMan",
    section: "income",
    sectionLabel: "収入",
    shortLabel: "売上",
    note: "PQ相当 / cash_inベース",
    kind: "money",
  },
  {
    key: "repairMan",
    section: "expense",
    sectionLabel: "出金",
    shortLabel: "修繕",
    note: "原状回復・リフォーム",
    kind: "money",
  },
  {
    key: "advertisingMan",
    section: "expense",
    sectionLabel: "出金",
    shortLabel: "広告",
    note: "広告料・募集まわり",
    kind: "money",
  },
  {
    key: "expenseMan",
    section: "expense",
    sectionLabel: "出金",
    shortLabel: "経費",
    note: "ステージング費用 / 空室対策費 / その他",
    kind: "money",
  },
  {
    key: "managementMan",
    section: "expense",
    sectionLabel: "出金",
    shortLabel: "管理費",
    note: "共用部の電気代 / 水道代 / インターネット代 / 管理会社",
    kind: "money",
  },
  {
    key: "acquisitionMan",
    section: "expense",
    sectionLabel: "出金",
    shortLabel: "取得時",
    note: "ローン手数料 / 火災保険 / 税理士費用など",
    kind: "money",
  },
  {
    key: "taxAccountantMan",
    section: "expense",
    sectionLabel: "出金",
    shortLabel: "税理士",
    note: "法人の定常支払",
    kind: "money",
  },
  {
    key: "loanRepaymentMan",
    section: "expense",
    sectionLabel: "出金",
    shortLabel: "返済",
    note: "ローン返済",
    kind: "money",
  },
  {
    key: "annualTaxMan",
    section: "expense",
    sectionLabel: "出金",
    shortLabel: "年払・税",
    note: "年払い・税金などの大口出金",
    kind: "money",
  },
  {
    key: "cashEndMan",
    section: "summary",
    sectionLabel: "残高",
    shortLabel: "月末現金",
    note: "cash_end がある月は実績優先",
    kind: "money",
  },
  {
    key: "netCashFlowMan",
    section: "summary",
    sectionLabel: "残高",
    shortLabel: "差引増減",
    note: "売上 - 出金",
    kind: "money",
  },
  {
    key: "repaymentRatio",
    section: "metric",
    sectionLabel: "参考",
    shortLabel: "返済比率",
    note: "返済 / 売上（参考）",
    kind: "ratio",
  },
];

function fmtCell(v: number | null, kind: "money" | "ratio"): string {
  if (v == null) return "—";
  if (kind === "money") return fmtMqMan(v);
  return `${v.toFixed(1)}%`;
}

export default function MqCashflowTable(props: Props) {
  const { title, year, rows, grainHint, unavailableReason } = props;
  let lastSection: RowSection | null = null;

  return (
    <div className="card mq-cashflow-card">
      <header className="mq-cashflow-header">
        <div>
          <span className="lvl">資金繰り</span>
          <strong>{title}</strong>
        </div>
        <div className="mq-cashflow-year-badge" aria-label={`表示年度 ${year}年`}>
          {year}年
        </div>
      </header>
      {grainHint ? <p className="meta mq-cashflow-meta">{grainHint}</p> : null}
      {unavailableReason ? (
        <p className="meta mq-cashflow-meta">{unavailableReason}</p>
      ) : null}
      <p className="meta mq-cashflow-meta">
        不動産実務の便宜分類です（厳密MQ定義とは一致しない可能性があります）。
        左の大項目で区切り、細かい説明は下の凡例にまとめています。
      </p>

      {unavailableReason ? null : (
        <>
          <div className="mq-cashflow-scroll">
            <table className="mq-table mq-cashflow-matrix">
              <thead>
                <tr>
                  <th className="mq-cashflow-sticky-col mq-cashflow-col-group">大項目</th>
                  <th className="mq-cashflow-sticky-col mq-cashflow-col-item">項目</th>
                  {rows.map((r) => (
                    <th key={r.month} className="num mq-cashflow-month-head">
                      {r.month.slice(5, 7)}月
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ROWS.map((item) => {
                  const showSection = item.section !== lastSection;
                  lastSection = item.section;
                  return (
                    <tr
                      key={item.key}
                      className={`mq-cashflow-row mq-cashflow-row-${item.section}${
                        showSection ? " mq-cashflow-row-section-start" : ""
                      }`}
                    >
                      <td
                        className={`mq-cashflow-sticky-col mq-cashflow-col-group mq-cashflow-section-${item.section}`}
                      >
                        {showSection ? item.sectionLabel : ""}
                      </td>
                      <td className="mq-cashflow-sticky-col mq-cashflow-col-item">
                        <strong>{item.shortLabel}</strong>
                      </td>
                      {rows.map((r) => {
                        const v = r[item.key];
                        const outVal =
                          item.key === "repaymentRatio" && v != null
                            ? (v as number) * 100
                            : (v as number | null);
                        return (
                          <td key={`${item.key}-${r.month}`} className="num">
                            {outVal == null ? "—" : fmtCell(outVal, item.kind)}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="mq-cashflow-notes">
            {ROWS.map((item) => (
              <div
                key={`note-${item.key}`}
                className={`mq-cashflow-note mq-cashflow-note-${item.section}`}
              >
                <div className="mq-cashflow-note-label">
                  {item.sectionLabel} · {item.shortLabel}
                </div>
                <div className="mq-cashflow-note-text">{item.note}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

