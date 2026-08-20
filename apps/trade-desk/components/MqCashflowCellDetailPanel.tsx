"use client";

import { useState } from "react";
import type { CashflowLineItem } from "@/lib/mqCashflowLineItems";
import { isLineItemReclassifiable, lineItemDisplayTag } from "@/lib/mqCashflowLineItems";
import { CASHFLOW_COLUMN_LABELS } from "@/lib/mqCashflowColumns";
import { fmtMqManSigned } from "@/lib/mqUnits";
import MqCashflowReclassifyMenu from "@/components/MqCashflowReclassifyMenu";

type Header = {
  month: string;
  columnKey: string;
  columnLabel: string;
  totalMan: number | null;
  txnCount: number;
  hasResidual: boolean;
};

type Props = {
  open: boolean;
  loading: boolean;
  error: string | null;
  header: Header | null;
  items: CashflowLineItem[];
  reclassifiable?: boolean;
  businessLine?: string;
  onClose: () => void;
  onReclassified: () => void;
};

function reasonLabel(reason: string): string {
  if (reason === "override") return "上書き";
  if (reason === "learned_rule") return "学習ルール";
  if (reason === "allowlist") return "事業費目";
  if (reason === "heuristic" || reason === "heuristic_loan") return "自動";
  if (reason === "residual") return "端数調整";
  if (reason === "manual") return "手動/参照";
  return reason;
}

export default function MqCashflowCellDetailPanel(props: Props) {
  const {
    open,
    loading,
    error,
    header,
    items,
    reclassifiable = false,
    businessLine = "realestate",
    onClose,
    onReclassified,
  } = props;

  const [activeItemId, setActiveItemId] = useState<string | null>(null);

  if (!open) return null;

  const activeItem = items.find((it) => it.id === activeItemId) ?? null;

  function handleReclassified() {
    setActiveItemId(null);
    onReclassified();
  }

  return (
    <>
      <button
        type="button"
        className="mq-cashflow-detail-backdrop"
        aria-label="内訳を閉じる"
        onClick={onClose}
      />
      <aside className="mq-cashflow-detail-panel" aria-label="セル内訳">
        <header className="mq-cashflow-detail-header">
          <div>
            <span className="lvl">内訳</span>
            <strong>
              {header
                ? `${header.columnLabel} · ${header.month.slice(0, 4)}年${header.month.slice(5, 7)}月`
                : "読込中…"}
            </strong>
          </div>
          <button type="button" className="btn" onClick={onClose}>
            閉じる
          </button>
        </header>

        {loading ? <p className="meta">読込中…</p> : null}
        {error ? <p className="meta" style={{ color: "var(--high)" }}>{error}</p> : null}

        {header && !loading && !error ? (
          <>
            <p className="meta mq-cashflow-detail-summary">
              表セル合計{" "}
              {header.totalMan == null
                ? "—"
                : fmtMqManSigned(
                    header.columnKey === "sales" ||
                      header.columnKey.startsWith("borrow_")
                      ? Math.abs(header.totalMan)
                      : -Math.abs(header.totalMan)
                  )}{" "}
              · 取引 {header.txnCount} 件
              {header.hasResidual ? " · 端数調整あり" : ""}
            </p>

            {items.length === 0 ? (
              <p className="meta">このセルに紐づく明細がありません。</p>
            ) : (
              <div className="mq-cashflow-detail-scroll">
                <table className="mq-table mq-cashflow-detail-table">
                  <thead>
                    <tr>
                      <th>日付</th>
                      <th>科目</th>
                      <th>店名・内容</th>
                      <th className="num">金額</th>
                      <th>列</th>
                      <th>根拠</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((it) => {
                      const canReclassify = reclassifiable && isLineItemReclassifiable(it);
                      const isActive = activeItemId === it.id;
                      return (
                        <tr
                          key={it.id}
                          className={[
                            it.source === "residual"
                              ? "mq-cashflow-detail-row-residual"
                              : "",
                            canReclassify ? "mq-cashflow-detail-row-reclassifiable" : "",
                            isActive ? "mq-cashflow-detail-row-active" : "",
                          ]
                            .filter(Boolean)
                            .join(" ")}
                          onClick={
                            canReclassify
                              ? () =>
                                  setActiveItemId(isActive ? null : it.id)
                              : undefined
                          }
                          onKeyDown={
                            canReclassify
                              ? (e) => {
                                  if (e.key === "Enter" || e.key === " ") {
                                    e.preventDefault();
                                    setActiveItemId(isActive ? null : it.id);
                                  }
                                }
                              : undefined
                          }
                          tabIndex={canReclassify ? 0 : undefined}
                          role={canReclassify ? "button" : undefined}
                          aria-expanded={canReclassify ? isActive : undefined}
                        >
                          <td>{it.txnDate ? String(it.txnDate).slice(0, 10) : "—"}</td>
                          <td>
                            {[it.category, it.subcategory].filter(Boolean).join(" / ") ||
                              "—"}
                          </td>
                          <td>
                            {it.place || "—"}
                            {lineItemDisplayTag(it) ? (
                              <span className="mq-cashflow-detail-tag">
                                {lineItemDisplayTag(it)}
                              </span>
                            ) : null}
                          </td>
                          <td className="num">{fmtMqManSigned(it.amountMan)}</td>
                          <td>{CASHFLOW_COLUMN_LABELS[it.columnKey]}</td>
                          <td title={it.classifyDetail || ""}>
                            {reasonLabel(it.classifyReason)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {activeItem && isLineItemReclassifiable(activeItem) ? (
              <MqCashflowReclassifyMenu
                item={activeItem}
                businessLine={businessLine}
                onDone={handleReclassified}
                onCancel={() => setActiveItemId(null)}
              />
            ) : null}

            {reclassifiable ? (
              <p className="meta" style={{ marginTop: 10 }}>
                取引行をクリックすると列を変更できます（端数調整・返済 tracker 行は不可）。
              </p>
            ) : null}
          </>
        ) : null}
      </aside>
    </>
  );
}
