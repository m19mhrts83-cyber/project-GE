"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { settleCardDebitFundMove } from "@/app/actions/cardDebitSettle";

export default function CardDebitSettleButton({ dueDate }: { dueDate: string }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);
  const due = (dueDate || "").trim().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(due)) return null;

  return (
    <span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
      <button
        type="button"
        className="btn primary"
        disabled={pending}
        onClick={() => {
          const ok = window.confirm(
            `${due} の寄せを完了としてウォッチを消しますか？\n（銀行送金が済んだ前提。カード引落そのものの完了ではありません）`,
          );
          if (!ok) return;
          start(async () => {
            const r = await settleCardDebitFundMove(due);
            setMsg(r.ok ? r.message || "寄せ完了" : r.error || "失敗");
            if (r.ok) router.refresh();
          });
        }}
      >
        {pending ? "処理中…" : "寄せ完了（アラート解除）"}
      </button>
      {msg ? <span className="meta">{msg}</span> : null}
    </span>
  );
}
