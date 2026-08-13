"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { yearLabel, yearOptions, type TaxScope } from "@/lib/taxInsights";

type Props = {
  scope: TaxScope;
  currentYear: number;
};

export default function TaxMetricsForm({ scope, currentYear }: Props) {
  const router = useRouter();
  const years = yearOptions(scope, currentYear, 5);
  const [fiscalYear, setFiscalYear] = useState(currentYear);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    const fd = new FormData(e.currentTarget);
    const body: Record<string, unknown> = {
      scope,
      fiscal_year: Number(fd.get("fiscal_year") || fiscalYear),
      filing_status: String(fd.get("filing_status") || "") || null,
      filed_on: String(fd.get("filed_on") || "") || null,
      note: String(fd.get("note") || "") || null,
      source: "manual",
    };
    if (scope === "personal") {
      body.taxable_income_jpy = fd.get("taxable_income_jpy") || null;
      body.income_tax_jpy = fd.get("income_tax_jpy") || null;
      body.refund_or_pay = String(fd.get("refund_or_pay") || "") || null;
    } else {
      body.revenue_jpy = fd.get("revenue_jpy") || null;
      body.ordinary_income_jpy = fd.get("ordinary_income_jpy") || null;
      body.corporate_tax_jpy = fd.get("corporate_tax_jpy") || null;
      body.tax_payable_jpy = fd.get("tax_payable_jpy") || null;
    }
    try {
      const res = await fetch("/api/tax/metrics", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMsg(String(json.error || `HTTP ${res.status}`));
        return;
      }
      setMsg("保存しました");
      router.refresh();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "保存に失敗");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="tax-metrics-form">
      <div className="tax-form-row">
        <label>
          年度
          <select
            name="fiscal_year"
            value={fiscalYear}
            onChange={(ev) => setFiscalYear(Number(ev.target.value))}
          >
            {years.map((y) => (
              <option key={y} value={y}>
                {yearLabel(scope, y)}
              </option>
            ))}
          </select>
        </label>
        <label>
          状態
          <select name="filing_status" defaultValue="filed">
            <option value="filed">申告済</option>
            <option value="draft">下書き</option>
            <option value="amended">更正</option>
            <option value="unknown">不明</option>
          </select>
        </label>
        <label>
          申告日
          <input type="date" name="filed_on" />
        </label>
      </div>

      {scope === "personal" ? (
        <div className="tax-form-row">
          <label>
            課税所得（円）
            <input name="taxable_income_jpy" type="number" inputMode="numeric" />
          </label>
          <label>
            所得税額（円）
            <input name="income_tax_jpy" type="number" inputMode="numeric" />
          </label>
          <label>
            還付／納付
            <select name="refund_or_pay" defaultValue="pay">
              <option value="pay">納付</option>
              <option value="refund">還付</option>
              <option value="zero">ゼロ</option>
            </select>
          </label>
        </div>
      ) : (
        <div className="tax-form-row">
          <label>
            売上高（円）
            <input name="revenue_jpy" type="number" inputMode="numeric" />
          </label>
          <label>
            経常利益（円）
            <input name="ordinary_income_jpy" type="number" inputMode="numeric" />
          </label>
          <label>
            法人税等（円）
            <input name="corporate_tax_jpy" type="number" inputMode="numeric" />
          </label>
          <label>
            納付額（円）
            <input name="tax_payable_jpy" type="number" inputMode="numeric" />
          </label>
        </div>
      )}

      <label className="tax-form-note">
        メモ
        <input name="note" type="text" placeholder="任意" />
      </label>

      <div className="tax-form-actions">
        <button type="submit" className="btn" disabled={busy}>
          {busy ? "保存中…" : `${scope === "corporate" ? "法人" : "個人"}の結果を登録`}
        </button>
        {msg ? <span className="meta">{msg}</span> : null}
      </div>
    </form>
  );
}
