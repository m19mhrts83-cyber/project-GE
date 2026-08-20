"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type Props = {
  year: string;
  entity: "personal" | "corporate";
  businessLine?: string;
  interestMan: number | null;
  taxMan: number | null;
  taxAccrualMonth?: "december" | "payment";
};

export default function MqCashflowTaxForm(props: Props) {
  const {
    year,
    entity,
    businessLine = "realestate",
    interestMan,
    taxMan,
    taxAccrualMonth = "december",
  } = props;
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [interest, setInterest] = useState(
    interestMan != null ? String(interestMan) : ""
  );
  const [tax, setTax] = useState(taxMan != null ? String(taxMan) : "");
  const defaultMonth = `${year}-12`;
  const [month, setMonth] = useState(defaultMonth);

  async function saveField(fieldKey: "interest_yearend" | "tax_payment", raw: string) {
    const amountMan = raw.trim() === "" ? 0 : Number(raw);
    if (!Number.isFinite(amountMan) || amountMan < 0) {
      throw new Error("金額は0以上の万円で入力してください");
    }
    const res = await fetch("/api/mq/cashflow/adjustments", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        businessLine,
        entity,
        periodMonth: month,
        fieldKey,
        amountMan,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "保存に失敗しました");
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      await saveField("interest_yearend", interest);
      await saveField("tax_payment", tax);
      setMsg("期末処理を保存しました。表を再計算します。");
      router.refresh();
    } catch (err) {
      setMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card mq-cashflow-tax-card">
      <header>
        <span className="lvl">期末</span>
        <strong>{year}年 · 利息・税金支払</strong>
      </header>
      <p className="meta" style={{ marginTop: 6 }}>
        既定は12月計上（資金不足を先に見る）。金額は万円。0で消えます。
        {taxAccrualMonth === "payment" ? " 計上方針: 支払月。" : ""}
      </p>
      <form className="mq-cashflow-tax-form" onSubmit={onSubmit}>
        <label>
          計上月
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            min={`${year}-01`}
            max={`${year}-12`}
          />
        </label>
        <label>
          利息（期末）
          <input
            type="number"
            min={0}
            step={1}
            placeholder="万円"
            value={interest}
            onChange={(e) => setInterest(e.target.value)}
          />
        </label>
        <label>
          税金支払
          <input
            type="number"
            min={0}
            step={1}
            placeholder="万円"
            value={tax}
            onChange={(e) => setTax(e.target.value)}
          />
        </label>
        <button type="submit" className="btn primary" disabled={busy}>
          {busy ? "保存中…" : "保存して再計算"}
        </button>
      </form>
      {msg ? <p className="meta" style={{ marginTop: 8 }}>{msg}</p> : null}
    </div>
  );
}
