"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { acknowledgeWatchAllAttention } from "@/app/actions/watchAck";

export default function WatchAckAllButton({ count }: { count: number }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  if (count <= 0) return null;

  return (
    <div className="watch-ack-wrap" style={{ marginBottom: 12 }}>
      <button
        type="button"
        className="btn"
        disabled={pending}
        onClick={() => {
          setErr(null);
          setMsg(null);
          start(async () => {
            const r = await acknowledgeWatchAllAttention();
            if (!r.ok) {
              setErr(r.error || "一括確認に失敗しました");
              return;
            }
            setMsg(r.message || "確認しました");
            router.refresh();
          });
        }}
      >
        {pending
          ? "更新中…"
          : `要確認・注意 ${count}件をすべて確認した`}
      </button>
      {err ? <p className="meta err">{err}</p> : null}
      {msg ? <p className="meta">{msg}</p> : null}
    </div>
  );
}
