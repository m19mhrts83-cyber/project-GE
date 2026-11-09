"use client";

import { useEffect, useState } from "react";
import { agoLabel, type DeskCard } from "@/lib/deskCore";

/** 見落とし（/misses?surface=triage）。仕分けが出さなかったものを、要対応だった／出さなくてよい で判断する */
type MissCard = DeskCard & { why: "auto_skip" | "not_surfaced" | "near_miss" };

const WHY: Record<MissCard["why"], string> = {
  auto_skip: "同じ送り手を2回見送ったので自動で見送り",
  not_surfaced: "Slack に出ないまま2日たった",
  near_miss: "Slack の枠に惜しくも入らなかった（次点）",
};

function uid(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }
}

export default function TriageMissesClient() {
  const [cards, setCards] = useState<MissCard[] | null>(null);
  const [done, setDone] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");

  useEffect(() => {
    fetch("/api/misses?surface=triage", { cache: "no-store" })
      .then((r) => r.json())
      .then((j) => {
        if (!j.ok) throw new Error(j.error || "読めませんでした");
        setCards(j.candidates || []);
      })
      .catch((e) => {
        setMsg(e instanceof Error ? e.message : String(e));
        setCards([]);
      });
  }, []);

  async function judge(c: MissCard, verdict: "miss" | "ok") {
    setDone((d) => ({ ...d, [c.id]: "…" }));
    try {
      const r = await fetch("/api/misses/judge", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ itemId: c.id, verdict, idemKey: `lw-miss-${uid()}`, why: c.why, subject: c.subject, partner: c.who, fromEmail: c.fromEmail }),
      });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || "失敗");
      setDone((d) => ({ ...d, [c.id]: verdict === "miss" ? "要対応に戻しました（判断デスクの先頭に出ます）" : "このままにしました" }));
    } catch (e) {
      setDone((d) => ({ ...d, [c.id]: "" }));
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="desk">
      <header>
        <div className="eyebrow acc">見落とし・メール</div>
        <strong className="desk-count">
          <b>{cards ? cards.filter((c) => !done[c.id]).length : "…"}</b> 件
        </strong>
      </header>
      <p className="meta">仕分けが「出さない」にしたものです。要対応だったものを教えてください。仕分けの直しに使います。</p>
      {msg ? <p className="meta" style={{ color: "var(--alert)" }}>{msg}</p> : null}
      {cards && !cards.length ? (
        <div className="glass desk-empty">
          <p className="desk-empty-title">見落とし候補はありません</p>
        </div>
      ) : null}
      {(cards || []).map((c) => (
        <article key={c.id} className="glass left-card" style={done[c.id] ? { opacity: 0.55 } : undefined}>
          <div className="desk-meta">
            <span>{c.who || c.fromEmail}</span>
            <span className="mono">{agoLabel(c.receivedAt)}</span>
            <span className="pill">{WHY[c.why]}</span>
          </div>
          <div className="left-subject">{c.subject}</div>
          {c.summary ? <p className="meta" style={{ margin: 0 }}>{c.summary}</p> : null}
          {done[c.id] ? (
            <p className="meta" style={{ margin: 0 }}>{done[c.id]}</p>
          ) : (
            <div className="btn-row">
              <button className="primary" onClick={() => void judge(c, "miss")}>要対応だった</button>
              <button onClick={() => void judge(c, "ok")}>出さなくてよい</button>
            </div>
          )}
        </article>
      ))}
    </div>
  );
}
