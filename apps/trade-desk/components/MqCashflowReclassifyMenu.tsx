"use client";

import { useState } from "react";
import type { CashflowLineItem } from "@/lib/mqCashflowLineItems";
import {
  CASHFLOW_COLUMN_LABELS,
  RECLASSIFY_COLUMN_OPTIONS,
  type CashflowColumnKey,
} from "@/lib/mqCashflowColumns";

const INCOME_COLUMNS = new Set<CashflowColumnKey>([
  "sales",
  "borrow_lt",
  "borrow_st",
  "borrow_officer",
]);

type Props = {
  item: CashflowLineItem;
  businessLine: string;
  onDone: () => void;
  onCancel: () => void;
};

export default function MqCashflowReclassifyMenu(props: Props) {
  const { item, businessLine, onDone, onCancel } = props;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [learnRule, setLearnRule] = useState(true);

  async function applyColumn(column: CashflowColumnKey) {
    if (!item.txnId || column === item.columnKey) {
      onCancel();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/mq/cashflow/txn-override", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          txnId: item.txnId,
          businessLine,
          cashflowColumn: column,
          learnRule,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "再分類に失敗しました");
      }
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function clearOverride() {
    if (!item.txnId) return;
    setBusy(true);
    setError(null);
    try {
      const q = new URLSearchParams({
        txnId: String(item.txnId),
        businessLine,
      });
      const res = await fetch(`/api/mq/cashflow/txn-override?${q}`, {
        method: "DELETE",
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "上書き解除に失敗しました");
      }
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const incomeOptions = RECLASSIFY_COLUMN_OPTIONS.filter((c) =>
    INCOME_COLUMNS.has(c)
  );
  const expenseOptions = RECLASSIFY_COLUMN_OPTIONS.filter(
    (c) => !INCOME_COLUMNS.has(c)
  );

  return (
    <div
      className="mq-cashflow-reclassify-menu"
      role="dialog"
      aria-label="列を変更"
    >
      <div className="mq-cashflow-reclassify-menu-header">
        <strong>列を変更</strong>
        <button
          type="button"
          className="btn mq-cashflow-reclassify-close"
          onClick={onCancel}
          disabled={busy}
          aria-label="閉じる"
        >
          ×
        </button>
      </div>
      <p className="meta mq-cashflow-reclassify-target">
        {item.place || "（摘要なし）"} · 現在:{" "}
        {CASHFLOW_COLUMN_LABELS[item.columnKey]}
      </p>
      <label className="mq-cashflow-reclassify-learn">
        <input
          type="checkbox"
          checked={learnRule}
          onChange={(e) => setLearnRule(e.target.checked)}
          disabled={busy}
        />
        同じ科目は今後もこの列へ（学習ルール）
      </label>
      {error ? (
        <p className="meta" style={{ color: "var(--high)" }}>
          {error}
        </p>
      ) : null}
      <div className="mq-cashflow-reclassify-groups">
        <div className="mq-cashflow-reclassify-group">
          <span className="mq-cashflow-reclassify-group-label">収入</span>
          <div className="mq-cashflow-reclassify-options">
            {incomeOptions.map((col) => (
              <button
                key={col}
                type="button"
                className={`mq-cashflow-reclassify-option${
                  col === item.columnKey
                    ? " mq-cashflow-reclassify-option-current"
                    : ""
                }`}
                disabled={busy || col === item.columnKey}
                onClick={() => applyColumn(col)}
              >
                {CASHFLOW_COLUMN_LABELS[col]}
              </button>
            ))}
          </div>
        </div>
        <div className="mq-cashflow-reclassify-group">
          <span className="mq-cashflow-reclassify-group-label">出金</span>
          <div className="mq-cashflow-reclassify-options">
            {expenseOptions.map((col) => (
              <button
                key={col}
                type="button"
                className={`mq-cashflow-reclassify-option${
                  col === item.columnKey
                    ? " mq-cashflow-reclassify-option-current"
                    : ""
                }`}
                disabled={busy || col === item.columnKey}
                onClick={() => applyColumn(col)}
              >
                {CASHFLOW_COLUMN_LABELS[col]}
              </button>
            ))}
          </div>
        </div>
      </div>
      {item.classifyReason === "override" ? (
        <button
          type="button"
          className="btn mq-cashflow-reclassify-reset"
          disabled={busy}
          onClick={clearOverride}
        >
          上書きを解除（自動分類に戻す）
        </button>
      ) : null}
      {busy ? <p className="meta">反映中…</p> : null}
    </div>
  );
}
