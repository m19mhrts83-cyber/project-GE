"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { acknowledgeRentStep } from "@/app/actions/rentStep";

export default function RentStepAckButton({
  targetMonth,
}: {
  targetMonth: string;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [err, setErr] = useState<string | null>(null);

  return (
    <div className="etc-ack-wrap">
      <button
        type="button"
        className="btn etc-ack-btn"
        disabled={pending || !targetMonth}
        onClick={() => {
          setErr(null);
          start(async () => {
            const r = await acknowledgeRentStep(targetMonth);
            if (!r.ok) {
              setErr(r.error || "確認に失敗しました");
              return;
            }
            router.refresh();
          });
        }}
      >
        {pending ? "更新中…" : "確認しました"}
      </button>
      {err ? <p className="meta etc-ack-err">{err}</p> : null}
    </div>
  );
}
