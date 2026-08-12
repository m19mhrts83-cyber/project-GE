"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function NewThemeForm() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [hypothesis, setHypothesis] = useState("");
  const [amount, setAmount] = useState("");
  const [funding, setFunding] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch("/api/themes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          hypothesis,
          amount_jpy: amount,
          funding_path: funding,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "失敗しました");
      } else {
        setTitle("");
        setHypothesis("");
        setAmount("");
        setFunding("");
        setMsg("草案を登録しました");
        router.refresh();
      }
    } catch (err) {
      setMsg(err instanceof Error ? err.message : "エラー");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="card" style={{ marginBottom: 16 }}>
      <header>
        <span className="lvl">手動</span>
        <strong>テーマ草案を追加</strong>
      </header>
      <label className="meta" htmlFor="t-title">
        タイトル
      </label>
      <input
        id="t-title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        required
        style={{
          width: "100%",
          marginBottom: 8,
          padding: 8,
          borderRadius: 8,
          border: "1px solid var(--line)",
          background: "#0f1419",
          color: "var(--ink)",
        }}
      />
      <label className="meta" htmlFor="t-hyp">
        仮説
      </label>
      <textarea
        id="t-hyp"
        value={hypothesis}
        onChange={(e) => setHypothesis(e.target.value)}
        rows={3}
        style={{
          width: "100%",
          marginBottom: 8,
          padding: 8,
          borderRadius: 8,
          border: "1px solid var(--line)",
          background: "#0f1419",
          color: "var(--ink)",
        }}
      />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input
          placeholder="金額（円・任意）"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          style={{
            flex: 1,
            minWidth: 140,
            padding: 8,
            borderRadius: 8,
            border: "1px solid var(--line)",
            background: "#0f1419",
            color: "var(--ink)",
          }}
        />
        <input
          placeholder="資金経路（任意）"
          value={funding}
          onChange={(e) => setFunding(e.target.value)}
          style={{
            flex: 2,
            minWidth: 180,
            padding: 8,
            borderRadius: 8,
            border: "1px solid var(--line)",
            background: "#0f1419",
            color: "var(--ink)",
          }}
        />
        <button type="submit" className="btn primary" disabled={busy}>
          {busy ? "送信中…" : "草案登録"}
        </button>
      </div>
      {msg ? <p className="meta">{msg}</p> : null}
    </form>
  );
}
