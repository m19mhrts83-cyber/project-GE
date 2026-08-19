import type { MqCashflowMonthRow } from "@/lib/mqCashflow";
import { fmtMqMan, fmtMqManSigned } from "@/lib/mqUnits";

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

type RowSign = "+" | "−" | "±" | "";

const ROWS: Array<{
  key: RowKey;
  section: RowSection;
  sectionLabel: string;
  sign: RowSign;
  shortLabel: string;
  note: string;
  kind: "money" | "ratio";
}> = [
  {
    key: "salesMan",
    section: "income",
    sectionLabel: "収入",
    sign: "+",
    shortLabel: "売上",
    note: "PQ相当 / cash_inベース（プラス）",
    kind: "money",
  },
  {
    key: "repairMan",
    section: "expense",
    sectionLabel: "出金",
    sign: "−",
    shortLabel: "修繕",
    note: "原状回復・リフォーム（マイナス）",
    kind: "money",
  },
  {
    key: "advertisingMan",
    section: "expense",
    sectionLabel: "出金",
    sign: "−",
    shortLabel: "広告",
    note: "広告料・募集まわり（マイナス）",
    kind: "money",
  },
  {
    key: "expenseMan",
    section: "expense",
    sectionLabel: "出金",
    sign: "−",
    shortLabel: "経費",
    note: "ステージング費用 / 空室対策費 / その他（マイナス）",
    kind: "money",
  },
  {
    key: "managementMan",
    section: "expense",
    sectionLabel: "出金",
    sign: "−",
    shortLabel: "管理費",
    note: "共用部の電気代 / 水道代 / インターネット代 / 管理会社（マイナス）",
    kind: "money",
  },
  {
    key: "acquisitionMan",
    section: "expense",
    sectionLabel: "出金",
    sign: "−",
    shortLabel: "取得時",
    note: "ローン手数料 / 火災保険 / 税理士費用など（マイナス）",
    kind: "money",
  },
  {
    key: "taxAccountantMan",
    section: "expense",
    sectionLabel: "出金",
    sign: "−",
    shortLabel: "税理士",
    note: "法人の定常支払（マイナス）",
    kind: "money",
  },
  {
    key: "loanRepaymentMan",
    section: "expense",
    sectionLabel: "出金",
    sign: "−",
    shortLabel: "返済",
    note: "ローン返済（マイナス）",
    kind: "money",
  },
  {
    key: "annualTaxMan",
    section: "expense",
    sectionLabel: "出金",
    sign: "−",
    shortLabel: "年払・税",
    note: "年払い・税金などの大口出金（マイナス）",
    kind: "money",
  },
  {
    key: "cashEndMan",
    section: "summary",
    sectionLabel: "残高",
    sign: "",
    shortLabel: "月末現金",
    note: "cash_end がある月は実績優先（残高・符号なし）",
    kind: "money",
  },
  {
    key: "netCashFlowMan",
    section: "summary",
    sectionLabel: "残高",
    sign: "±",
    shortLabel: "差引増減",
    note: "売上 − 出金（プラス/マイナス）",
    kind: "money",
  },
  {
    key: "repaymentRatio",
    section: "metric",
    sectionLabel: "参考",
    sign: "",
    shortLabel: "返済比率",
    note: "返済 / 売上（参考・比率）",
    kind: "ratio",
  },
];

function fmtCell(
  v: number | null,
  item: (typeof ROWS)[number]
): string {
  if (v == null) return "—";
  if (item.kind === "ratio") return `${v.toFixed(1)}%`;
  if (item.key === "cashEndMan") return fmtMqMan(v);
  if (item.key === "netCashFlowMan") return fmtMqManSigned(v);
  if (item.section === "income") return fmtMqManSigned(Math.abs(v));
  if (item.section === "expense") return fmtMqManSigned(-Math.abs(v));
  return fmtMqMan(v);
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
        収入は<strong className="mq-cashflow-sign-plus">＋</strong>、出金は
        <strong className="mq-cashflow-sign-minus">−</strong>
        で表示します。左の符号列と金額の符号で確認できます。
      </p>

      {unavailableReason ? null : (
        <>
          <div className="mq-cashflow-scroll">
            <table className="mq-table mq-cashflow-matrix">
              <thead>
                <tr>
                  <th className="mq-cashflow-sticky-col mq-cashflow-col-group">大項目</th>
                  <th className="mq-cashflow-sticky-col mq-cashflow-col-sign">符号</th>
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
                      <td
                        className={`mq-cashflow-sticky-col mq-cashflow-col-sign mq-cashflow-sign-${item.sign === "+" ? "plus" : item.sign === "−" ? "minus" : item.sign === "±" ? "pm" : "none"}`}
                        aria-label={
                          item.sign === "+"
                            ? "プラス（収入）"
                            : item.sign === "−"
                              ? "マイナス（出金）"
                              : item.sign === "±"
                                ? "増減"
                                : undefined
                        }
                      >
                        {item.sign || "—"}
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
                        const cellClass =
                          item.section === "income"
                            ? "mq-cashflow-cell-plus"
                            : item.section === "expense"
                              ? "mq-cashflow-cell-minus"
                              : item.key === "netCashFlowMan" && outVal != null
                                ? outVal >= 0
                                  ? "mq-cashflow-cell-plus"
                                  : "mq-cashflow-cell-minus"
                                : "";
                        return (
                          <td
                            key={`${item.key}-${r.month}`}
                            className={`num ${cellClass}`.trim()}
                          >
                            {outVal == null ? "—" : fmtCell(outVal, item)}
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
                  {item.sign ? `${item.sign} ` : ""}
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

