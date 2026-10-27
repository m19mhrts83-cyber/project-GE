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
  const [queued, setQueued] = useState(false);

  async function onClick() {
    if (requireConfirm) {
      const text =
        confirmMessage ||
        "この操作は本番データに影響します。本当にキューへ入れますか？";
      if (!window.confirm(text)) {
        setMsg("キャンセルしました");
        setQueued(false);
        return;
      }
    }
    setBusy(true);
    setMsg(null);
    setQueued(false);
    try {
      const bodyPayload = {
        ...(payload ?? {}),
        ...(requireConfirm
          ? {
              ui_confirmed: true,
              ui_confirmed_at: new Date().toISOString(),
              // Zaim / 計画補正 apply 等の API ゲートと揃える
              confirm_apply: true,
            }
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
        setQueued(true);
        setMsg("キューに入れました。Mac のバックグラウンドワーカーが実行します。");
        router.refresh();
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(false);
    }
  }

  return (
    // span で包む: 呼び出し側が <p> の中に置くことが多く、<div> だとハイドレーションエラー（#418）になる
    <span style={{ display: "inline-block", marginRight: 8, marginBottom: 8 }}>
      <button
        type="button"
        className={requireConfirm ? "btn primary" : "btn"}
        disabled={busy}
        onClick={onClick}
      >
        {busy ? "送信中…" : label || title}
      </button>
      {msg ? (
        <span
          className="meta"
          style={{ display: "block", marginTop: 6, maxWidth: 420 }}
        >
          {msg}
          {queued ? (
            <>
              <br />
              結果は <a href="/jobs">ジョブ</a> 画面で「待ち → 実行中 →
              完了／失敗」を確認できます（Mac が起きているときに実行）。
            </>
          ) : null}
        </span>
      ) : null}
    </span>
  );
}
