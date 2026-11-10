"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import DecisionNotePanel from "@/components/DecisionNotePanel";
import type { DecisionNote } from "@/lib/kurashiftDecision";

const ALLOWED: Record<string, string[]> = {
  draft: ["consulting", "approved", "cancelled"],
  consulting: ["draft", "approved", "cancelled"],
  approved: ["executing", "done", "consulting", "cancelled"],
  executing: ["done", "cancelled"],
  done: ["cancelled"],
  cancelled: ["draft"],
};

/** 判断メモを出す遷移（お金の判断そのもの）。実行中へ・草案に戻すは進み具合なので出さない */
const NEEDS_NOTE = new Set(["approved", "consulting", "cancelled", "done"]);

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

  const [pending, setPending] = useState<string | null>(null);
  const labelOf = (s: string) =>
    s === "done" && !isCardBuffer ? "完了" : LABELS[s] || s;

  function hintFor(next: string): string | undefined {
    if (next === "approved") {
      return "承認＝計画合意のみ（記帳はしません）。\n次: Jarvisが入力 → あなたが最終画面確認 → OTP＋実行ボタン。送金用Chromeは完了後に閉じます。";
    }
    if (next === "done" && isCardBuffer) {
      return "寄せ完了としてウォッチを消します（銀行側の送金が済んだ前提。引落日そのものの完了ではありません）。";
    }
    if (next === "cancelled") return "この資金移動をやめます。";
    if (next === "consulting") return "決めきれないので相談に回します。何が引っかかったかを残すと次の案が良くなります。";
    return undefined;
  }

  function onPick(next: string) {
    if (NEEDS_NOTE.has(next)) {
      setPending(next);
      setMsg(null);
      return;
    }
    void setStatus(next, null);
  }

  async function setStatus(next: string, decision: DecisionNote | null) {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch(`/api/money-ops/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: next, decision }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "失敗");
      } else {
        setMsg(
          next === "done" && isCardBuffer
            ? "寄せ完了・ウォッチ解除"
            : `${labelOf(next)} にしました（判断ログに記録）`
        );
        setPending(null);
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
          disabled={busy || pending !== null}
          onClick={() => onPick(s)}
          style={{ fontSize: 12, padding: "4px 8px" }}
        >
          {labelOf(s)}
        </button>
      ))}
      {msg ? <span className="meta">{msg}</span> : null}
      {pending ? (
        <div style={{ flexBasis: "100%" }}>
          <DecisionNotePanel
            title={`「${labelOf(pending)}」にします`}
            hint={hintFor(pending)}
            tagKind="money"
            confirmLabel={pending === "approved" ? "承認する" : "決める"}
            busy={busy}
            onConfirm={(d) => void setStatus(pending, d)}
            onCancel={() => setPending(null)}
          />
        </div>
      ) : null}
    </div>
  );
}
