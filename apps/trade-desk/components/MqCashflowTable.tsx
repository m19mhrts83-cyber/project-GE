import type { MqCashflowMonthRow } from "@/lib/mqCashflow";
import { fmtMqMan } from "@/lib/mqUnits";

type Props = {
  title: string;
  year: string; // 表示用
  rows: MqCashflowMonthRow[];
  grainHint?: string; // 例: "年次の選択年（各月）"
  unavailableReason?: string | null;
};

const ROWS: Array<{
  key:
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
  shortLabel: string;
  note: string;
  kind: "money" | "ratio";
}> = [
  {
    key: "salesMan",
    shortLabel: "売上",
    note: "PQ相当 / cash_inベース",
    kind: "money",
  },
  {
    key: "repairMan",
    shortLabel: "修繕",
    note: "原状回復・リフォーム",
    kind: "money",
  },
  {
    key: "advertisingMan",
    shortLabel: "広告",
    note: "広告料・募集まわり",
    kind: "money",
  },
  {
    key: "expenseMan",
    shortLabel: "経費",
    note: "ステージング費用 / 空室対策費 / その他",
    kind: "money",
  },
  {
    key: "managementMan",
    shortLabel: "管理費",
    note: "共用部の電気代 / 水道代 / インターネット代 / 管理会社",
    kind: "money",
  },
  {
    key: "acquisitionMan",
    shortLabel: "取得時",
    note: "ローン手数料 / 火災保険 / 税理士費用など",
    kind: "money",
  },
  {
    key: "taxAccountantMan",
    shortLabel: "税理士",
    note: "法人の定常支払",
    kind: "money",
  },
  {
    key: "loanRepaymentMan",
    shortLabel: "返済",
    note: "ローン返済",
    kind: "money",
  },
  {
    key: "annualTaxMan",
    shortLabel: "年払・税",
    note: "年払い・税金などの大口出金",
    kind: "money",
  },
  {
    key: "cashEndMan",
    shortLabel: "月末現金",
    note: "cash_end がある月は実績優先",
    kind: "money",
  },
  {
    key: "netCashFlowMan",
    shortLabel: "差引増減",
    note: "売上 - 出金",
    kind: "money",
  },
  {
    key: "repaymentRatio",
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
  const { title, rows, grainHint, unavailableReason } = props;

  return (
    <div className="card" style={{ marginTop: 16, padding: "18px 18px 16px" }}>
      <header>
        <span className="lvl">MQ補助（資金繰り）</span>
        <strong>{title}</strong>
      </header>
      {grainHint ? <p className="meta">{grainHint}</p> : null}
      {unavailableReason ? (
        <p className="meta" style={{ marginTop: 6 }}>
          {unavailableReason}
        </p>
      ) : null}
      <p className="meta" style={{ marginTop: 6 }}>
        不動産実務の便宜分類です（厳密MQ定義とは一致しない可能性があります）。
        表は視認性重視で短い見出しにし、細かい説明は下の凡例に逃がしています。
      </p>

      {unavailableReason ? null : (
        <>
          <div style={{ overflowX: "auto", marginTop: 10 }}>
            <table className="mq-table mq-cashflow-matrix" style={{ minWidth: 940 }}>
              <thead>
                <tr>
                  <th className="mq-cashflow-sticky-col">項目</th>
                  {rows.map((r) => (
                    <th key={r.month} className="num">
                      {r.month.slice(5, 7)}月
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ROWS.map((item) => (
                  <tr key={item.key}>
                    <td className="mq-cashflow-sticky-col">
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
                ))}
              </tbody>
            </table>
          </div>

          <div className="mq-cashflow-notes">
            {ROWS.map((item) => (
              <div key={`note-${item.key}`} className="mq-cashflow-note">
                <div className="mq-cashflow-note-label">{item.shortLabel}</div>
                <div className="mq-cashflow-note-text">{item.note}</div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

