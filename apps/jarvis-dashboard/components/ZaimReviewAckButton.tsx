"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { acknowledgeZaimReview } from "@/app/actions/zaimWatch";

export default function ZaimReviewAckButton({
  batchId,
  className,
}: {
  /** 空でも可（確認待ちの直し一式を潰す） */
  batchId?: string;
  className?: string;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [err, setErr] = useState<string | null>(null);

  return (
    <div className={className || "etc-ack-wrap"}>
      <button
        type="button"
        className="btn etc-ack-btn"
        disabled={pending}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setErr(null);
          start(async () => {
            const r = await acknowledgeZaimReview(batchId || "");
            if (!r.ok) {
              setErr(r.error || "確認に失敗しました");
              return;
            }
            router.refresh();
          });
        }}
      >
        {pending ? "更新中…" : "確認した"}
      </button>
      {err ? <p className="meta etc-ack-err">{err}</p> : null}
    </div>
  );
}
