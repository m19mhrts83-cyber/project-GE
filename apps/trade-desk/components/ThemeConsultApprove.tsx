"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

/**
 * 相談内容を見たうえでテーマを承認する本線アクション。
 */
export default function ThemeConsultApprove({
  themeId,
  themeStatus,
}: {
  themeId: string;
  themeStatus: string;
}) {
  const router = useRouter();
  const [decision, setDecision] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  if (themeStatus !== "consulting") {
    return (
      <p className="meta">
        テーマ状態: <strong>{themeStatus}</strong>
        {themeStatus === "approved" || themeStatus === "executing"
          ? " — 承認済み。完走アシストはテーマ一覧から。"
          : null}
      </p>
    );
  }

  async function approve() {
    const ok = window.confirm(
      "相談内容を確認したうえで、このテーマを承認しますか？\n（実弾・振替は自動では動きません。承認後に「完走アシスト」をキューしてください）"
    );
    if (!ok) return;
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch(`/api/themes/${themeId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status: "approved",
          approved_via: "consult_review",
          decision:
            decision.trim() ||
            "相談内容を確認のうえ承認",
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "失敗");
      } else {
        setMsg("承認しました");
        router.refresh();
        router.push(`/themes/${themeId}`);
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      style={{
        marginTop: 16,
        padding: 14,
        background: "var(--accent-soft)",
        borderRadius: "var(--radius)",
        border: "1px solid var(--line)",
      }}
    >
      <strong style={{ display: "block", marginBottom: 8 }}>
        内容確認のうえ承認
      </strong>
      <p className="meta" style={{ marginTop: 0 }}>
        上の相談メモを読んでから押してください。判断メモは相談記録の「判断」に残ります。
      </p>
      <label className="meta" style={{ display: "block", marginBottom: 6 }}>
        判断メモ（任意）
      </label>
      <textarea
        value={decision}
        onChange={(e) => setDecision(e.target.value)}
        rows={3}
        placeholder="例: 年1RBは今月は見送り／配分は現状維持で承認"
        style={{
          width: "100%",
          maxWidth: 560,
          font: "inherit",
          padding: 8,
          borderRadius: 6,
          border: "1px solid var(--line)",
          marginBottom: 10,
        }}
      />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button
          type="button"
          className="btn primary"
          disabled={busy}
          onClick={approve}
          style={{
            minHeight: 48,
            minWidth: 220,
            width: "100%",
            maxWidth: 420,
            fontSize: 16,
            touchAction: "manipulation",
          }}
        >
          {busy ? "処理中…" : "相談内容を確認して承認する"}
        </button>
        <a
          className="btn"
          href="/themes"
          style={{
            minHeight: 48,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            minWidth: 140,
            touchAction: "manipulation",
          }}
        >
          テーマ一覧へ
        </a>
      </div>
      <p className="meta" style={{ marginTop: 8 }}>
        スマホでも同じ確認ダイアログ → 承認。実弾は自動では動きません。
      </p>
      {msg ? <p className="meta">{msg}</p> : null}
    </div>
  );
}
