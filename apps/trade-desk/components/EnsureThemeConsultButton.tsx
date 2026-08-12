"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function EnsureThemeConsultButton({
  themeId,
}: {
  themeId: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function ensure() {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch(`/api/themes/${themeId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ensure_consultation: true }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "失敗");
      } else {
        router.refresh();
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ marginTop: 8 }}>
      <button
        type="button"
        className="btn primary"
        disabled={busy}
        onClick={ensure}
        style={{ fontSize: 12, padding: "4px 8px" }}
      >
        {busy ? "作成中…" : "相談メモを作成する"}
      </button>
      {msg ? <span className="meta"> {msg}</span> : null}
    </div>
  );
}
