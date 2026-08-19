import type { MqCashflowMonthRow } from "@/lib/mqCashflow";
import { fmtMqMan } from "@/lib/mqUnits";

type Props = {
  title: string;
  year: string; // 表示用
  rows: MqCashflowMonthRow[];
  grainHint?: string; // 例: "年次の選択年（各月）"
  unavailableReason?: string | null;
};

const COLS: Array<{
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
  label: string;
  kind: "money" | "ratio";
}> = [
  { key: "salesMan", label: "売上（PQ相当 / cash_in）", kind: "money" },
  { key: "repairMan", label: "修繕費用（原状回復・リフォーム）", kind: "money" },
  { key: "advertisingMan", label: "広告料", kind: "money" },
  { key: "expenseMan", label: "経費（ステージング費用 / 空室対策費 / その他）", kind: "money" },
  {
    key: "managementMan",
    label: "管理費（共用部の電気代 / 水道代 / インターネット代 / 管理会社）",
    kind: "money",
  },
  {
    key: "acquisitionMan",
    label: "取得時費用（ローン手数料 / 火災保険 / 税理士費用など）",
    kind: "money",
  },
  {
    key: "taxAccountantMan",
    label: "税理士報酬（法人の定常支払）",
    kind: "money",
  },
  { key: "loanRepaymentMan", label: "ローン返済", kind: "money" },
  { key: "annualTaxMan", label: "年払い・税金などの大口出金", kind: "money" },
  { key: "cashEndMan", label: "月末現金", kind: "money" },
  { key: "netCashFlowMan", label: "差引キャッシュ増減（売上-出金）", kind: "money" },
  { key: "repaymentRatio", label: "返済比率（参考）", kind: "ratio" },
];

function fmtCell(v: number | null, kind: "money" | "ratio"): string {
  if (v == null) return "—";
  if (kind === "money") return fmtMqMan(v);
  return `${v.toFixed(1)}%`;
}

export default function MqCashflowTable(props: Props) {
  const { title, rows, grainHint, unavailableReason } = props;

  return (
    <div className="card" style={{ marginTop: 16 }}>
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
        経費側は「ローン返済を除く出金」を、クリックしない1段要約として
        修繕/広告/経費/管理費/取得時/税理士/年払いに分けています。
      </p>

      {unavailableReason ? null : (
        <div style={{ overflowX: "auto", marginTop: 10 }}>
          <table className="mq-table" style={{ minWidth: 980 }}>
            <thead>
              <tr>
                <th style={{ position: "sticky", left: 0, background: "white" }}>月</th>
                {COLS.map((c) => (
                  <th key={c.key} className="num">
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.month}>
                  <td style={{ position: "sticky", left: 0, background: "white" }}>
                    {r.month}
                  </td>
                  {COLS.map((c) => {
                    const v = r[c.key];
                    // repaymentRatio は格納値が “fraction” 想定なので補正
                    const outVal =
                      c.key === "repaymentRatio" && v != null
                        ? (v as number) * 100
                        : (v as number | null);

                    return (
                      <td key={c.key} className="num">
                        {outVal == null ? "—" : fmtCell(outVal, c.kind)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

