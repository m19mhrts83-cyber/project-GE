"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function NewMoneyOpForm() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch("/api/money-ops", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: fd.get("title"),
          kind: fd.get("kind"),
          rationale: fd.get("rationale"),
          from_account: fd.get("from_account"),
          to_account: fd.get("to_account"),
          amount_jpy: fd.get("amount_jpy"),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "失敗");
      } else {
        setMsg("草案を作成しました");
        e.currentTarget.reset();
        router.refresh();
      }
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "エラー");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={onSubmit} style={{ marginBottom: 16 }}>
      <header>
        <span className="lvl">新規</span>
        <strong>資金移動・手続きドラフト</strong>
      </header>
      <p className="meta">
        承認後も自動振込はしません。保険配分変更は手順アシストのみ。
      </p>
      <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
        <input name="title" required placeholder="タイトル" />
        <select name="kind" defaultValue="bank_transfer">
          <option value="bank_transfer">口座間振込</option>
          <option value="broker_transfer">証券への入出金</option>
          <option value="securities_cash">証券口座内の資金移動</option>
          <option value="insurance_alloc">保険積立率・配分（アシストのみ）</option>
        </select>
        <input name="from_account" placeholder="From（口座名）" />
        <input name="to_account" placeholder="To（口座名）" />
        <input name="amount_jpy" type="number" placeholder="金額（円）" />
        <textarea name="rationale" placeholder="理由・背景" rows={3} />
        <button type="submit" className="btn primary" disabled={busy}>
          草案を作る
        </button>
        {msg ? <span className="meta">{msg}</span> : null}
      </div>
    </form>
  );
}
