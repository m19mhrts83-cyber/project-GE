"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { ackMqMonthClose } from "@/app/actions/mqMonthCloseAck";

export default function MqMonthCloseAckButton({ month }: { month: string }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [err, setErr] = useState<string | null>(null);

  return (
    <span>
      <button
        type="button"
        className="btn"
        disabled={pending}
        onClick={() => {
          setErr(null);
          start(async () => {
            const r = await ackMqMonthClose(month);
            if (!r.ok) {
              setErr(r.error || "失敗");
              return;
            }
            router.refresh();
          });
        }}
      >
        {pending ? "処理中…" : "まとめた／確認した"}
      </button>
      {err ? <span className="meta"> {err}</span> : null}
    </span>
  );
}
