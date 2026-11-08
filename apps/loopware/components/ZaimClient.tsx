"use client";

import { useEffect, useState } from "react";
import type { ZaimFix } from "@/lib/zaimCore";

/**
 * Zaim の週次見直し。Jarvis が学習して直した費目を 正しい／違う で確かめる。
 * 違う は理由を一言だけ（任意）。違うにした店は Mac の学習係が次から直さない。
 */
function uid(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }
}

export default function ZaimClient() {
  const [fixes, setFixes] = useState<ZaimFix[] | null>(null);
  const [done, setDone] = useState<Record<string, string>>({});
  const [note, setNote] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");

  useEffect(() => {
    fetch("/api/zaim", { cache: "no-store" })
      .then((r) => r.json())
      .then((j) => {
        if (!j.ok) throw new Error(j.error || "読めませんでした");
        setFixes(j.fixes || []);
      })
      .catch((e) => {
        setMsg(e instanceof Error ? e.message : String(e));
        setFixes([]);
      });
  }, []);

  async function judge(f: ZaimFix, verdict: "good" | "wrong") {
    const r = await fetch("/api/zaim", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: f.id, verdict, note: note[f.id] || "", idemKey: `lw-zaim-${uid()}` }),
    });
    const j = await r.json().catch(() => ({}));
    if (!j.ok) {
      setMsg(j.error || "記録できませんでした");
      return;
    }
    setDone((d) => ({ ...d, [f.id]: verdict === "good" ? "正しいにしました" : "違うにしました（次から直しません）" }));
  }

  const left = fixes ? fixes.filter((f) => !done[f.id]).length : null;

  return (
    <div className="desk">
      <header>
        <div className="eyebrow acc">Zaim の見直し</div>
        <strong className="desk-count">
          <b>{left ?? "…"}</b> 件
        </strong>
      </header>
      <p className="meta">Jarvis が学習して直した費目です。合っていれば「正しい」、ずれていれば「違う」。</p>
      {msg ? <p className="meta" style={{ color: "var(--alert)" }}>{msg}</p> : null}
      {fixes && !fixes.length ? (
        <div className="glass desk-empty">
          <p className="desk-empty-title">確かめる直しはありません</p>
        </div>
      ) : null}
      {(fixes || []).map((f) => (
        <article key={f.id} className="glass left-card" style={done[f.id] ? { opacity: 0.6 } : undefined}>
          <div className="left-subject">{f.proposal || f.shop || f.id}</div>
          {done[f.id] ? (
            <p className="meta" style={{ margin: 0 }}>{done[f.id]}</p>
          ) : (
            <>
              <input
                type="text"
                placeholder="違うときの一言（任意）"
                value={note[f.id] || ""}
                onChange={(e) => setNote((n) => ({ ...n, [f.id]: e.target.value }))}
              />
              <div className="btn-row">
                <button className="primary" onClick={() => void judge(f, "good")}>正しい</button>
                <button onClick={() => void judge(f, "wrong")}>違う</button>
              </div>
            </>
          )}
        </article>
      ))}
    </div>
  );
}
