"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function EnqueueJobButton({
  jobType,
  title,
  payload,
  label,
  requireConfirm,
  confirmMessage,
}: {
  jobType: string;
  title: string;
  payload?: Record<string, unknown>;
  label?: string;
  /** 本番反映など危険操作。true のとき confirm 後に ui_confirmed を付与 */
  requireConfirm?: boolean;
  confirmMessage?: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function onClick() {
    if (requireConfirm) {
      const text =
        confirmMessage ||
        "この操作は本番データに影響します。本当にキューへ入れますか？";
      if (!window.confirm(text)) {
        setMsg("キャンセルしました");
        return;
      }
    }
    setBusy(true);
    setMsg(null);
    try {
      const bodyPayload = {
        ...(payload ?? {}),
        ...(requireConfirm
          ? { ui_confirmed: true, ui_confirmed_at: new Date().toISOString() }
          : {}),
      };
      const res = await fetch("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_type: jobType,
          title,
          payload: bodyPayload,
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
      <button
        type="button"
        className={requireConfirm ? "btn primary" : "btn"}
        disabled={busy}
        onClick={onClick}
      >
        {busy ? "送信中…" : label || title}
      </button>
      {msg ? <div className="meta">{msg}</div> : null}
    </div>
  );
}
