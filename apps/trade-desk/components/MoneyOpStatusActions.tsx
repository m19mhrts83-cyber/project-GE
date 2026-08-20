"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const ALLOWED: Record<string, string[]> = {
  draft: ["consulting", "approved", "cancelled"],
  consulting: ["draft", "approved", "cancelled"],
  approved: ["executing", "done", "consulting", "cancelled"],
  executing: ["done", "cancelled"],
  done: ["cancelled"],
  cancelled: ["draft"],
};

const LABELS: Record<string, string> = {
  consulting: "相談中へ",
  approved: "承認",
  executing: "実行中へ",
  done: "寄せ完了（ウォッチ解除）",
  cancelled: "取消",
  draft: "草案に戻す",
};

export default function MoneyOpStatusActions({
  id,
  status,
  kind,
}: {
  id: string;
  status: string;
  kind?: string | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const nexts = ALLOWED[status] || [];
  const isCardBuffer = kind === "card_settlement_buffer";

  async function setStatus(next: string) {
    if (next === "approved") {
      const ok = window.confirm(
        "この資金移動を承認しますか？\n（承認＝計画合意のみ。記帳はしません。\n次: Jarvisが入力 → あなたが最終画面確認 → OTP＋実行ボタン。\n送金用Chromeは完了後に閉じます）"
      );
      if (!ok) return;
    }
    if (next === "done" && isCardBuffer) {
      const ok = window.confirm(
        "寄せ完了としてウォッチを消しますか？\n（銀行側の送金が済んだ前提。引落日そのものの完了ではありません）"
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
        setMsg(
          next === "done" && isCardBuffer
            ? "寄せ完了・ウォッチ解除"
            : `${next} に更新`
        );
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
          className={
            s === "approved" || (s === "done" && isCardBuffer)
              ? "btn primary"
              : "btn"
          }
          disabled={busy}
          onClick={() => setStatus(s)}
          style={{ fontSize: 12, padding: "4px 8px" }}
        >
          {s === "done" && !isCardBuffer ? "完了" : LABELS[s] || s}
        </button>
      ))}
      {msg ? <span className="meta">{msg}</span> : null}
    </div>
  );
}
