"use client";

import { useState } from "react";
import type { CashflowActionKind } from "@/lib/mqCashflowManual";
import { actionKindLabel } from "@/lib/mqCashflowManual";

type Props = {
  open: boolean;
  year: string;
  entity: "personal" | "corporate";
  businessLine?: string;
  defaultMonth?: string;
  onClose: () => void;
  onSaved: () => void;
};

export default function MqCashflowActionModal(props: Props) {
  const {
    open,
    year,
    entity,
    businessLine = "realestate",
    defaultMonth,
    onClose,
    onSaved,
  } = props;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [month, setMonth] = useState(defaultMonth || `${year}-08`);
  const [kind, setKind] = useState<CashflowActionKind>("officer");
  const [amount, setAmount] = useState("50");
  const [label, setLabel] = useState("");

  if (!open) return null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const amountMan = Number(amount);
    if (!Number.isFinite(amountMan) || amountMan <= 0) {
      setError("金額は正の万円で入力してください");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/mq/cashflow/actions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          businessLine,
          entity,
          periodMonth: month,
          actionKind: kind,
          amountMan,
          label:
            label.trim() ||
            `${month} ${actionKindLabel(kind)} ${amountMan}万（計画）`,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "追加に失敗しました");
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="mq-cashflow-detail-backdrop"
        aria-label="閉じる"
        onClick={onClose}
      />
      <div
        className="mq-cashflow-action-modal"
        role="dialog"
        aria-label="処置を追加"
      >
        <header>
          <strong>処置を追加（シミュレーション）</strong>
          <button type="button" className="btn" onClick={onClose}>
            閉じる
          </button>
        </header>
        <p className="meta">
          計画上の資金調達です。実績の借入列とは別に「処置」行へ入り、以降の月末現金を再計算します。
        </p>
        <form onSubmit={submit} className="mq-cashflow-tax-form">
          <label>
            月
            <input
              type="month"
              value={month}
              min={`${year}-01`}
              max={`${year}-12`}
              onChange={(e) => setMonth(e.target.value)}
            />
          </label>
          <label>
            種別
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value as CashflowActionKind)}
            >
              <option value="officer">個人借入</option>
              <option value="borrow_st">短期借入</option>
              <option value="borrow_lt">長期借入</option>
            </select>
          </label>
          <label>
            金額（万円）
            <input
              type="number"
              min={1}
              step={1}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </label>
          <label>
            メモ
            <input
              type="text"
              maxLength={200}
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="任意"
            />
          </label>
          {error ? (
            <p className="meta" style={{ color: "var(--high)" }}>
              {error}
            </p>
          ) : null}
          <button type="submit" className="btn primary" disabled={busy}>
            {busy ? "追加中…" : "追加して再計算"}
          </button>
        </form>
      </div>
    </>
  );
}
