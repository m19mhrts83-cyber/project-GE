"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function MqMonthCloseNoticeCard({
  title,
  body,
  href,
  cashflowHref,
  targetMonth,
  statusLabel,
}: {
  title: string;
  body: string;
  href: string;
  cashflowHref?: string;
  targetMonth: string;
  statusLabel?: "取込待ち" | "自動更新済み" | "要確認" | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function ack() {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch("/api/mq/month-close-ack", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ month: targetMonth }),
      });
      const json = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMsg(String(json.error || `HTTP ${res.status}`));
        return;
      }
      setMsg("確認済みにしました");
      router.refresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "失敗");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="notice" style={{ marginBottom: 12 }}>
      <strong>{title}</strong>
      {statusLabel ? (
        <p className="meta" style={{ margin: "4px 0 0" }}>
          状態: {statusLabel}
        </p>
      ) : null}
      <p style={{ margin: "6px 0 10px" }}>{body}</p>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <a className="btn primary" href={href}>
          MQ会計評価へ
        </a>
        {cashflowHref ? (
          <a className="btn" href={cashflowHref}>
            資金繰り表へ
          </a>
        ) : null}
        <button type="button" className="btn" disabled={busy} onClick={ack}>
          {busy ? "処理中…" : "まとめた／確認した"}
        </button>
      </div>
      {msg ? (
        <p className="meta" style={{ marginTop: 6 }}>
          {msg}
        </p>
      ) : null}
    </div>
  );
}
