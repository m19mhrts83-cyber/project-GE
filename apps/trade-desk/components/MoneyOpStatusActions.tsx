"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const ALLOWED: Record<string, string[]> = {
  draft: ["consulting", "approved", "cancelled"],
  consulting: ["draft", "approved", "cancelled"],
  approved: ["executing", "consulting", "cancelled"],
  executing: ["done", "cancelled"],
  done: ["cancelled"],
  cancelled: ["draft"],
};

const LABELS: Record<string, string> = {
  consulting: "相談中へ",
  approved: "承認",
  executing: "実行中へ",
  done: "完了",
  cancelled: "取消",
  draft: "草案に戻す",
};

export default function MoneyOpStatusActions({
  id,
  status,
}: {
  id: string;
  status: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const nexts = ALLOWED[status] || [];

  async function setStatus(next: string) {
    if (next === "approved") {
      const ok = window.confirm(
        "この資金移動を承認しますか？\n（銀行・証券の振込確定は自動では動きません。手順アシストに従って手動実行してください）"
      );
      if (!ok) return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch(`/api/money-ops/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: next }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "失敗");
      } else {
        setMsg(`${next} に更新`);
        router.refresh();
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(false);
    }
  }

  if (nexts.length === 0) return null;

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
      {nexts.map((s) => (
        <button
          key={s}
          type="button"
          className={s === "approved" ? "btn primary" : "btn"}
          disabled={busy}
          onClick={() => setStatus(s)}
          style={{ fontSize: 12, padding: "4px 8px" }}
        >
          {LABELS[s] || s}
        </button>
      ))}
      {msg ? <span className="meta">{msg}</span> : null}
    </div>
  );
}
