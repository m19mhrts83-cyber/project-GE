"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const ALLOWED: Record<string, string[]> = {
  draft: ["consulting", "approved", "closed"],
  // consulting の「承認」は一覧では出さず、確認画面へ誘導
  consulting: ["draft", "closed"],
  approved: ["executing", "consulting", "closed"],
  executing: ["reviewed", "closed"],
  reviewed: ["closed"],
  closed: ["draft"],
};

const LABELS: Record<string, string> = {
  consulting: "相談中へ",
  approved: "承認（相談スキップ）",
  executing: "実行中へ",
  reviewed: "振り返り済",
  closed: "閉じる",
  draft: "草案に戻す",
};

export default function ThemeStatusActions({
  id,
  status,
  consultationId,
}: {
  id: string;
  status: string;
  consultationId?: string | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const nexts = ALLOWED[status] || [];

  async function setStatus(next: string) {
    if (next === "approved") {
      const ok = window.confirm(
        "相談を挟まずにこのテーマを承認しますか？\n（実弾は動きません。通常は「相談中へ」→内容確認→承認を推奨）"
      );
      if (!ok) return;
    }
    if (next === "consulting") {
      const ok = window.confirm(
        "相談中にします。相談メモを作成（または既存を紐づけ）し、内容確認画面へ進みます。"
      );
      if (!ok) return;
    }
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch(`/api/themes/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status: next,
          approved_via: next === "approved" ? "theme_list_skip_consult" : undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "失敗");
      } else {
        setMsg(`${next} に更新`);
        if (next === "consulting") {
          router.push(`/themes/${id}`);
          return;
        }
        router.refresh();
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
      {status === "consulting" ? (
        <a
          className="btn primary"
          href={`/themes/${id}`}
          style={{ fontSize: 12, padding: "4px 8px" }}
        >
          相談内容を確認して承認 →
        </a>
      ) : null}
      {status === "consulting" && consultationId ? (
        <a
          className="btn"
          href={`/consultations/${consultationId}`}
          style={{ fontSize: 12, padding: "4px 8px" }}
        >
          相談記録
        </a>
      ) : null}
      {nexts.map((s) => (
        <button
          key={s}
          type="button"
          className={s === "approved" ? "btn" : "btn"}
          disabled={busy}
          onClick={() => setStatus(s)}
          style={{ fontSize: 12, padding: "4px 8px" }}
        >
          {LABELS[s] || s}
        </button>
      ))}
      {msg ? <span className="meta">{msg}</span> : null}
    </div>
  );
}
