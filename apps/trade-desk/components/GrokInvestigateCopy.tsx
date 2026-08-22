"use client";

import { useState } from "react";
import { buildGrokInvestigatePrompt } from "@/lib/reInquiryShared";

/** KURASHIFT deals → 不動産賃貸チーム（参謀）へ路線価・HZ 追加調査を依頼するコピー */
export default function GrokInvestigateCopy({
  dealId,
  title,
  area,
  priceMan,
  summaryJson,
  alreadyGrok,
}: {
  dealId: string;
  title: string;
  area?: string | null;
  priceMan?: number | null;
  summaryJson?: Record<string, unknown> | null;
  /** 既に mail_grok 調査がある場合は再調査ラベル */
  alreadyGrok?: boolean;
}) {
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function copy() {
    setBusy(true);
    setMsg(null);
    try {
      const text = buildGrokInvestigatePrompt({
        title,
        area,
        priceMan,
        summaryJson,
        dealId,
      });
      await navigator.clipboard.writeText(text);
      setMsg("コピー済 → Grok「不動産賃貸チーム」へ貼付");
    } catch {
      setMsg("コピー失敗（ブラウザ権限を確認）");
    } finally {
      setBusy(false);
    }
  }

  const label = alreadyGrok ? "路線価・HZ 再調査" : "路線価・HZ 追加調査";

  return (
    <div style={{ marginTop: 4 }}>
      <button
        type="button"
        className="btn"
        style={{ fontSize: 11, padding: "2px 6px" }}
        disabled={busy}
        onClick={copy}
        title="クリップボードへ。Grok 不動産賃貸チーム（または参謀）に貼ると調査追加になります"
      >
        {busy ? "…" : label}
      </button>
      {msg ? (
        <span className="meta" style={{ marginLeft: 6 }}>
          {msg}
        </span>
      ) : null}
    </div>
  );
}
