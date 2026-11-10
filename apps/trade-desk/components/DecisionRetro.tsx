"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { RETRO_QUALITY, type RetroQuality } from "@/lib/kurashiftDecision";

/**
 * 後日の答え合わせ（S21）。進めた判断が、実際どうだったかを1タップで残す。
 * 「やり直したい」のときだけ、ひとことを聞く。
 */
export default function DecisionRetro({
  kind,
  targetId,
  refId,
  compact,
}: {
  kind: "money" | "deal";
  targetId: string;
  refId: string;
  compact?: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [ask, setAsk] = useState<RetroQuality | null>(null);
  const [note, setNote] = useState("");
  const [done, setDone] = useState<RetroQuality | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(!compact);

  async function send(quality: RetroQuality, text: string) {
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch("/api/decisions/retro", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind, targetId, refId, quality, note: text }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErr(data.error || "残せませんでした");
      } else {
        setDone(quality);
        setAsk(null);
        router.refresh();
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return <span className={`retro-badge q-${done}`}>答え合わせ：{RETRO_QUALITY[done]}</span>;
  }
  if (!open) {
    return (
      <button type="button" className="retro-open" onClick={() => setOpen(true)}>
        答え合わせ
      </button>
    );
  }

  return (
    <div className="retro">
      <div className="retro-buttons">
        {(Object.keys(RETRO_QUALITY) as RetroQuality[]).map((q) => (
          <button
            key={q}
            type="button"
            className={`retro-btn q-${q}${ask === q ? " on" : ""}`}
            disabled={busy}
            onClick={() => (q === "good" ? void send(q, "") : setAsk(q))}
          >
            {RETRO_QUALITY[q]}
          </button>
        ))}
      </div>
      {ask ? (
        <div className="retro-note">
          <input
            type="text"
            className="dn-input"
            autoFocus
            placeholder="次に同じ判断をするとき、覚えておくことは？（任意）"
            value={note}
            maxLength={400}
            onChange={(e) => setNote(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.nativeEvent.isComposing) void send(ask, note);
            }}
          />
          <button type="button" className="dn-confirm" disabled={busy} onClick={() => void send(ask, note)}>
            {busy ? "…" : "残す"}
          </button>
        </div>
      ) : null}
      {err ? <div className="meta">{err}</div> : null}
    </div>
  );
}
