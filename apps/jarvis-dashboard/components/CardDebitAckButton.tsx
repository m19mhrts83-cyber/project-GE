"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { acknowledgeCardDebitDue } from "@/app/actions/cardDebitAck";

export default function CardDebitAckButton({ dueDate }: { dueDate: string }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<string | null>(null);
  const due = (dueDate || "").trim().slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(due)) return null;

  return (
    <span style={{ display: "inline-flex", gap: 8, alignItems: "center" }}>
      <button
        type="button"
        className="btn"
        disabled={pending}
        onClick={() => {
          start(async () => {
            const r = await acknowledgeCardDebitDue(due);
            setMsg(r.ok ? r.message || "確認済" : r.error || "失敗");
            if (r.ok) router.refresh();
          });
        }}
      >
        {pending ? "処理中…" : `${due} を確認（ピン解除）`}
      </button>
      {msg ? <span className="meta">{msg}</span> : null}
    </span>
  );
}
