"use client";

import { useState } from "react";
import { buildGrokInvestigatePrompt } from "@/lib/reInquiryShared";

export default function GrokInvestigateCopy({
  dealId,
  title,
  area,
  priceMan,
  summaryJson,
}: {
  dealId: string;
  title: string;
  area?: string | null;
  priceMan?: number | null;
  summaryJson?: Record<string, unknown> | null;
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
      });
      await navigator.clipboard.writeText(text);
      setMsg("Grok調査用をコピーしました");
    } catch {
      setMsg("コピー失敗（ブラウザ権限を確認）");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ marginTop: 4 }}>
      <button
        type="button"
        className="btn"
        style={{ fontSize: 11, padding: "2px 6px" }}
        disabled={busy}
        onClick={copy}
        title={`deal ${dealId}`}
      >
        {busy ? "…" : "Grok調査用コピー"}
      </button>
      {msg ? (
        <span className="meta" style={{ marginLeft: 6 }}>
          {msg}
        </span>
      ) : null}
    </div>
  );
}
