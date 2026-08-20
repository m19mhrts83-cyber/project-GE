"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import type { MqCashflowMonthRow } from "@/lib/mqCashflow";
import { fmtMqMan, fmtMqManSigned } from "@/lib/mqUnits";
import {
  CLICKABLE_ROW_FIELDS,
  rowFieldToColumn,
  type CashflowLineItem,
} from "@/lib/mqCashflowLineItems";
import MqCashflowCellDetailPanel from "@/components/MqCashflowCellDetailPanel";

type Props = {
  title: string;
  year: string;
  rows: MqCashflowMonthRow[];
  grainHint?: string;
  unavailableReason?: string | null;
  originHint?: string | null;
  negativeMonths?: { month: string; cashEndMan: number }[];
  businessLine?: string;
  entity?: string;
  interactive?: boolean;
  onAddAction?: () => void;
};

type RowKey = keyof Pick<
  MqCashflowMonthRow,
  | "cashBeginMan"
  | "salesMan"
  | "borrowLtMan"
  | "borrowStMan"
  | "borrowOfficerMan"
  | "repairMan"
  | "advertisingMan"
  | "expenseMan"
  | "managementMan"
  | "acquisitionMan"
  | "taxAccountantMan"
  | "loanRepaymentMan"
  | "annualTaxMan"
  | "interestYearendMan"
  | "taxPaymentMan"
  | "actionInflowMan"
  | "cashEndMan"
  | "netCashFlowMan"
  | "yearendCarryMan"
  | "repaymentRatio"
>;

type RowSection = "balance" | "income" | "expense" | "summary" | "metric";

type RowSign = "+" | "−" | "±" | "→" | "";

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
    key: "cashBeginMan",
    section: "balance",
    sectionLabel: "残高",
    sign: "",
    shortLabel: "期首残高",
    note: "1月=起点設定、2月以降=前月末現金（万円）",
    kind: "money",
  },
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
    key: "borrowLtMan",
    section: "income",
    sectionLabel: "収入",
    sign: "+",
    shortLabel: "長期借入",
    note: "物件融資等の実行（プラス）",
    kind: "money",
  },
  {
    key: "borrowStMan",
    section: "income",
    sectionLabel: "収入",
    sign: "+",
    shortLabel: "短期借入",
    note: "フリー・教育ローン等・事業用（プラス）",
    kind: "money",
  },
  {
    key: "borrowOfficerMan",
    section: "income",
    sectionLabel: "収入",
    sign: "+",
    shortLabel: "個人借入",
    note: "役員借入・個人持出（プラス）",
    kind: "money",
  },
  {
    key: "actionInflowMan",
    section: "income",
    sectionLabel: "収入",
    sign: "+",
    shortLabel: "処置",
    note: "シミュレーション上の資金調達（プラス）",
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
    note: "ローン手数料 / 保証料 / 登記など取得時諸費用（マイナス）",
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
    note: "年払い・固都税 / 火災保険更新などの大口出金（マイナス）",
    kind: "money",
  },
  {
    key: "interestYearendMan",
    section: "expense",
    sectionLabel: "出金",
    sign: "−",
    shortLabel: "利息",
    note: "期末利息支払（12月・マイナス）",
    kind: "money",
  },
  {
    key: "taxPaymentMan",
    section: "expense",
    sectionLabel: "出金",
    sign: "−",
    shortLabel: "税金",
    note: "法人税等の手入力（12月・マイナス）",
    kind: "money",
  },
  {
    key: "netCashFlowMan",
    section: "summary",
    sectionLabel: "残高",
    sign: "±",
    shortLabel: "差引増減",
    note: "収入合計 − 出金合計（プラス/マイナス）",
    kind: "money",
  },
  {
    key: "cashEndMan",
    section: "summary",
    sectionLabel: "残高",
    sign: "",
    shortLabel: "月末現金",
    note: "期末現金残高。マイナス時は警告表示",
    kind: "money",
  },
  {
    key: "yearendCarryMan",
    section: "summary",
    sectionLabel: "残高",
    sign: "→",
    shortLabel: "翌年繰越",
    note: "12月末現金→翌年1月期首へ自動引継ぎ",
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
  if (
    item.key === "cashBeginMan" ||
    item.key === "cashEndMan" ||
    item.key === "yearendCarryMan"
  ) {
    return fmtMqMan(v);
  }
  if (item.key === "netCashFlowMan") return fmtMqManSigned(v);
  if (item.section === "income") return fmtMqManSigned(Math.abs(v));
  if (item.section === "expense") return fmtMqManSigned(-Math.abs(v));
  return fmtMqMan(v);
}

export default function MqCashflowTable(props: Props) {
  const {
    title,
    year,
    rows,
    grainHint,
    unavailableReason,
    originHint,
    negativeMonths = [],
    businessLine = "realestate",
    entity = "corporate",
    interactive = true,
    onAddAction,
  } = props;

  const [panelOpen, setPanelOpen] = useState(false);
  const [panelLoading, setPanelLoading] = useState(false);
  const [panelError, setPanelError] = useState<string | null>(null);
  const [panelHeader, setPanelHeader] = useState<{
    month: string;
    columnKey: string;
    columnLabel: string;
    totalMan: number | null;
    txnCount: number;
    hasResidual: boolean;
  } | null>(null);
  const [panelItems, setPanelItems] = useState<CashflowLineItem[]>([]);
  const [panelReclassifiable, setPanelReclassifiable] = useState(false);
  const detailContextRef = useRef<{
    month: string;
    rowKey: RowKey;
    cellTotal: number;
  } | null>(null);

  const router = useRouter();

  const fetchCellDetail = useCallback(
    async (month: string, rowKey: RowKey, cellTotal: number) => {
      const column = rowFieldToColumn(rowKey);
      if (!column) return;

      setPanelLoading(true);
      setPanelError(null);

      try {
        const q = new URLSearchParams({
          month,
          column,
          entity,
          line: businessLine,
          cellTotalMan: String(cellTotal),
        });
        const res = await fetch(`/api/mq/cashflow/cell-detail?${q.toString()}`);
        const data = await res.json();
        if (!res.ok) {
          throw new Error(data.error || "内訳の取得に失敗しました");
        }
        setPanelHeader(data.header);
        setPanelItems(data.items ?? []);
        setPanelReclassifiable(Boolean(data.reclassifiable));
      } catch (e) {
        setPanelError(e instanceof Error ? e.message : String(e));
      } finally {
        setPanelLoading(false);
      }
    },
    [businessLine, entity]
  );

  const openCellDetail = useCallback(
    async (month: string, rowKey: RowKey, cellTotal: number | null) => {
      const column = rowFieldToColumn(rowKey);
      if (!column || cellTotal == null) return;

      detailContextRef.current = { month, rowKey, cellTotal };
      setPanelOpen(true);
      setPanelLoading(true);
      setPanelError(null);
      setPanelHeader(null);
      setPanelItems([]);
      setPanelReclassifiable(false);

      await fetchCellDetail(month, rowKey, cellTotal);
    },
    [fetchCellDetail]
  );

  const handleReclassified = useCallback(async () => {
    router.refresh();
    const ctx = detailContextRef.current;
    if (ctx) {
      await fetchCellDetail(ctx.month, ctx.rowKey, ctx.cellTotal);
    }
  }, [router, fetchCellDetail]);

  let lastSection: RowSection | null = null;

  const negativeSet = new Set(negativeMonths.map((n) => n.month));

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
      {originHint ? (
        <p className="meta mq-cashflow-meta">{originHint}</p>
      ) : null}
      {unavailableReason ? (
        <p className="meta mq-cashflow-meta">{unavailableReason}</p>
      ) : null}
      {negativeMonths.length > 0 ? (
        <div className="mq-cashflow-alert-banner" role="alert">
          ⚠️ 現金がマイナスの月:{" "}
          {negativeMonths
            .map((n) => `${n.month.slice(5, 7)}月（${fmtMqManSigned(n.cashEndMan)}）`)
            .join(" · ")}
          {" — 処置を追加してください"}
          {onAddAction ? (
            <>
              {" "}
              <button type="button" className="btn primary" onClick={onAddAction}>
                処置を追加
              </button>
            </>
          ) : null}
        </div>
      ) : null}
      <p className="meta mq-cashflow-meta">
        帳簿起点の現金推移です。収入は<strong className="mq-cashflow-sign-plus">＋</strong>
        、出金は
        <strong className="mq-cashflow-sign-minus">−</strong>
        で表示します。
        {interactive && !unavailableReason
          ? " 金額セルをクリックすると内訳が表示されます。"
          : ""}
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
                    <th
                      key={r.month}
                      className={`num mq-cashflow-month-head${
                        negativeSet.has(r.month) ? " mq-cashflow-alert-negative" : ""
                      }`}
                    >
                      {r.month.slice(5, 7)}月
                      {negativeSet.has(r.month) ? " ⚠" : ""}
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
                      }${item.key === "actionInflowMan" ? " mq-cashflow-row-virtual" : ""}`}
                    >
                      <td
                        className={`mq-cashflow-sticky-col mq-cashflow-col-group mq-cashflow-section-${item.section}`}
                      >
                        {showSection ? item.sectionLabel : ""}
                      </td>
                      <td
                        className={`mq-cashflow-sticky-col mq-cashflow-col-sign mq-cashflow-sign-${item.sign === "+" ? "plus" : item.sign === "−" ? "minus" : item.sign === "±" ? "pm" : item.sign === "→" ? "carry" : "none"}`}
                      >
                        {item.sign || "—"}
                      </td>
                      <td className="mq-cashflow-sticky-col mq-cashflow-col-item">
                        <strong>{item.shortLabel}</strong>
                      </td>
                      {rows.map((r) => {
                        const v = r[item.key] as number | null;
                        const outVal =
                          item.key === "repaymentRatio" && v != null
                            ? v * 100
                            : v;
                        const isNegCell =
                          item.key === "cashEndMan" && r.isNegative;
                        const cellClass =
                          isNegCell
                            ? "mq-cashflow-alert-negative"
                            : item.section === "income"
                              ? "mq-cashflow-cell-plus"
                              : item.section === "expense"
                                ? "mq-cashflow-cell-minus"
                                : item.key === "netCashFlowMan" && outVal != null
                                  ? outVal >= 0
                                    ? "mq-cashflow-cell-plus"
                                    : "mq-cashflow-cell-minus"
                                  : "";
                        const clickable =
                          interactive &&
                          item.kind === "money" &&
                          CLICKABLE_ROW_FIELDS.has(item.key) &&
                          outVal != null;

                        const cellInner =
                          outVal == null ? "—" : fmtCell(outVal, item);

                        return (
                          <td
                            key={`${item.key}-${r.month}`}
                            className={`num ${cellClass}${clickable ? " mq-cashflow-cell-clickable" : ""}`.trim()}
                          >
                            {clickable ? (
                              <button
                                type="button"
                                className="mq-cashflow-cell-btn"
                                onClick={() =>
                                  openCellDetail(r.month, item.key, outVal as number)
                                }
                              >
                                {cellInner}
                              </button>
                            ) : (
                              cellInner
                            )}
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

      <MqCashflowCellDetailPanel
        open={panelOpen}
        loading={panelLoading}
        error={panelError}
        header={panelHeader}
        items={panelItems}
        reclassifiable={panelReclassifiable}
        businessLine={businessLine}
        onClose={() => {
          setPanelOpen(false);
          detailContextRef.current = null;
        }}
        onReclassified={handleReclassified}
      />
    </div>
  );
}
