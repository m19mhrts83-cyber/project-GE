"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function EnqueueJobButton({
  jobType,
  title,
  payload,
  label,
}: {
  jobType: string;
  title: string;
  payload?: Record<string, unknown>;
  label?: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function onClick() {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_type: jobType,
          title,
          payload: payload ?? {},
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "失敗しました");
      } else {
        setMsg("キューに入れました。Mac worker が実行します。");
        router.refresh();
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "inline-block", marginRight: 8, marginBottom: 8 }}>
      <button type="button" className="btn" disabled={busy} onClick={onClick}>
        {busy ? "送信中…" : label || title}
      </button>
      {msg ? <div className="meta">{msg}</div> : null}
    </div>
  );
}
