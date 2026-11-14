"use client";

import { useEffect, useState } from "react";
import LogJar, { type Bead } from "./LogJar";
import { logged } from "@/lib/logPulse";
import { STAY_REASON_TAGS, type WeekTally } from "@/lib/decisionContract";
import { agoLabel, type DeskCard, type NextStep } from "@/lib/deskCore";

/**
 * 残り案件（/desk?surface=triage&view=left）。
 * 迷ったもの・時間がなくて見ていないものを NG にせず、型で「次の一手」を出して 良い／違う で決める。
 * 違うときだけ、残っている理由を（任意で）聞く。
 */
type LeftCard = DeskCard & { next: NextStep };

const STAY = (Object.keys(STAY_REASON_TAGS) as (keyof typeof STAY_REASON_TAGS)[]).map((k) => ({ k, label: STAY_REASON_TAGS[k] }));

function uid(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }
}

export default function LeftClient() {
  const [cards, setCards] = useState<LeftCard[] | null>(null);
  const [tallyWeek, setTallyWeek] = useState<WeekTally | null>(null);
  const [beads, setBeads] = useState<Bead[]>([]);
  const [dash, setDash] = useState("https://jarvis-dashboard-amber.vercel.app");
  const [state, setState] = useState<Record<string, "busy" | "done" | "ask" | "err">>({});
  const [msg, setMsg] = useState("");
  const [shownAt] = useState(() => new Date().toISOString());

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch("/api/desk?surface=triage&view=left", { cache: "no-store" });
        const j = await r.json();
        if (!j.ok) throw new Error(j.error || "読めませんでした");
        setCards(j.cards || []);
        setTallyWeek(j.tally || null);
        if (j.dashboard) setDash(j.dashboard);
      } catch (e) {
        setMsg(e instanceof Error ? e.message : String(e));
        setCards([]);
      }
    })();
  }, []);

  async function judge(c: LeftCard, verdict: "good" | "wrong", stayReason?: string) {
    setState((s) => ({ ...s, [c.id]: "busy" }));
    if (verdict === "good" && c.next.effect === "reply") {
      window.open(`${dash}/mail/${encodeURIComponent(c.id)}`, "_blank", "noopener");
    }
    try {
      const r = await fetch("/api/desk/next", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          itemId: c.id,
          verdict,
          idemKey: `lw-next-${uid()}`,
          step: c.next,
          stayReason: stayReason || c.stayReason,
          subject: c.subject,
          partner: c.who,
          timing: { shown_at: shownAt, decided_at: new Date().toISOString() },
        }),
      });
      const j = await r.json();
      if (!j.ok) throw new Error(j.error || "失敗");
      setBeads((b) => [...b, verdict === "good" ? "take" : "note"]);
      logged({ beads: [verdict === "good" ? "take" : "note"], label: verdict === "good" ? "この次でよい" : "違うと記録しました" });
      setState((s) => ({ ...s, [c.id]: verdict === "wrong" && !stayReason ? "ask" : "done" }));
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
      setState((s) => ({ ...s, [c.id]: "err" }));
    }
  }

  async function tellReason(c: LeftCard, reason: string) {
    setState((s) => ({ ...s, [c.id]: "done" }));
    // 理由だけを1行足す（同じ案件の「違う」の補足）
    await fetch("/api/log", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        decision: {
          surface: "triage",
          action: "comment",
          source: "loopware",
          targetType: "triage_item",
          targetId: c.id,
          stayReason: reason,
          idemKey: `lw-stay-${uid()}`,
          payload: { about: "next_wrong", next_step_id: c.next.id },
        },
      }),
    }).catch(() => undefined);
  }

  const open = (cards || []).filter((c) => state[c.id] !== "done");

  return (
    <div className="desk">
      <header className="desk-top">
        <div>
          <div className="eyebrow acc">残り・次の一手</div>
          <strong className="desk-count">
            <b>{cards ? open.length : "…"}</b> 件
          </strong>
        </div>
        <LogJar week={tallyWeek} session={beads} />
      </header>
      <p className="meta">迷ったもの・24時間たったものです。NG にはしません。次の一手が合っていれば「良い」、違えば「違う」。</p>
      {msg ? <p className="meta" style={{ color: "var(--alert)" }}>{msg}</p> : null}

      {cards && !open.length ? (
        <div className="glass desk-empty">
          <div className="eyebrow acc" style={{ color: "var(--positive)" }}>ALL CLEAR</div>
          <p className="desk-empty-title">残りはありません</p>
          <a className="meta" href="/desk?surface=triage">判断デスクへ戻る</a>
        </div>
      ) : null}

      {open.map((c) => (
        <article key={c.id} className="glass left-card">
          <div className="desk-meta">
            <span>{c.who || c.fromEmail}</span>
            <span className="mono">{agoLabel(c.receivedAt)}</span>
            {c.hesitatedAt ? <span className="pill hes">迷った</span> : <span className="pill">未判断</span>}
            {c.stayReason ? <span className="pill">{STAY_REASON_TAGS[c.stayReason as keyof typeof STAY_REASON_TAGS]}</span> : null}
          </div>
          <a className="left-subject" href={`/desk?surface=triage&item=${encodeURIComponent(c.id)}`}>{c.subject}</a>
          <div className="next-step">
            <span className="eyebrow">次の一手</span>
            <p>{c.next.text}</p>
            <span className="meta">理由: {c.next.why}</span>
          </div>
          {state[c.id] === "ask" ? (
            <div className="desk-reason" style={{ padding: 0 }}>
              <p className="meta">残っている理由は？（任意）</p>
              <div className="tags">
                {STAY.map((t) => (
                  <button key={t.k} className="tag" onClick={() => void tellReason(c, t.k)}>{t.label}</button>
                ))}
                <button className="tag" onClick={() => setState((s) => ({ ...s, [c.id]: "done" }))}>答えない</button>
              </div>
            </div>
          ) : (
            <div className="btn-row">
              <button className="primary" disabled={state[c.id] === "busy"} onClick={() => void judge(c, "good")}>良い</button>
              <button disabled={state[c.id] === "busy"} onClick={() => void judge(c, "wrong")}>違う</button>
            </div>
          )}
        </article>
      ))}
    </div>
  );
}
