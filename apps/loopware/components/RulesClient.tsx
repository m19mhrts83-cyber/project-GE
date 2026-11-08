"use client";

import { useEffect, useState } from "react";
import { LADDER, ladderStep, type AdoptedRule, type RuleCandidate } from "@/lib/rules";

/**
 * 今週の学び（ルール候補）。土曜の週次分析が最大3件置く。
 * 採用＝承認（PR を見直さなくてよい）／今回だけ／違う（8週間出さない）。採用したものは「取り消す」で戻せる。
 */
function uid(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }
}

const VERDICT_LABEL = { accept: "採用しました。ルール帳に入ります", once: "今回だけにしました", reject: "違うにしました（8週間出しません）" };

export default function RulesClient() {
  const [week, setWeek] = useState<string | null>(null);
  const [cands, setCands] = useState<RuleCandidate[] | null>(null);
  const [adopted, setAdopted] = useState<AdoptedRule[]>([]);
  const [decided, setDecided] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");

  useEffect(() => {
    fetch("/api/rules", { cache: "no-store" })
      .then((r) => r.json())
      .then((j) => {
        if (!j.ok) throw new Error(j.error || "読めませんでした");
        setWeek(j.week);
        setCands(j.candidates || []);
        setAdopted(j.adopted || []);
        const d: Record<string, string> = {};
        for (const id of j.decided || []) d[id] = "判断済み";
        setDecided(d);
      })
      .catch((e) => {
        setMsg(e instanceof Error ? e.message : String(e));
        setCands([]);
      });
  }, []);

  async function send(body: Record<string, unknown>): Promise<boolean> {
    const r = await fetch("/api/rules/decide", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ ...body, idemKey: `lw-rule-${uid()}` }) });
    const j = await r.json().catch(() => ({}));
    if (!j.ok) setMsg(j.error || "記録できませんでした");
    return Boolean(j.ok);
  }

  async function decide(c: RuleCandidate, verdict: "accept" | "once" | "reject") {
    if (await send({ verdict, candidate: c })) setDecided((d) => ({ ...d, [c.id]: VERDICT_LABEL[verdict] }));
  }

  async function revert(a: AdoptedRule) {
    if (!a.ruleId) return;
    if (await send({ verdict: "revert", ruleId: a.ruleId, employee: a.employee, text: a.text })) {
      setAdopted((xs) => xs.map((x) => (x.decisionId === a.decisionId ? { ...x, reverted: true } : x)));
    }
  }

  return (
    <div className="desk">
      <header>
        <div className="eyebrow acc">今週の学び{week ? `・${week}` : ""}</div>
        <strong className="desk-count">
          <b>{cands ? cands.filter((c) => !decided[c.id]).length : "…"}</b> 件
        </strong>
      </header>
      <p className="meta">あなたの判断から見つけたルールの候補です。「採用」1回で反映します（あとから取り消せます）。月曜まで答えがなければ保留のままにします。</p>
      {msg ? <p className="meta" style={{ color: "var(--alert)" }}>{msg}</p> : null}
      {cands && !cands.length ? (
        <div className="glass desk-empty">
          <p className="desk-empty-title">今週の候補はありません</p>
          <p className="meta">土曜の朝に、その週の判断ログから最大3件届きます。</p>
        </div>
      ) : null}

      {(cands || []).map((c) => (
        <article key={c.id} className="glass left-card" style={decided[c.id] ? { opacity: 0.6 } : undefined}>
          <div className="ladder" aria-label={`自律度 ${LADDER[ladderStep(c)]}`}>
            {LADDER.map((l, i) => (
              <span key={l} className={i <= ladderStep(c) ? "on" : ""} title={l} />
            ))}
            <em>{LADDER[ladderStep(c)]}</em>
          </div>
          <div className="left-subject">{c.text}</div>
          <p className="meta" style={{ margin: 0 }}>根拠: {c.why}</p>
          {c.rule_line ? <code className="rule-line">{c.rule_line}</code> : null}
          {c.needs_ai ? <p className="meta" style={{ margin: 0 }}>言い回しの文言は、採用後に差分から決めます。</p> : null}
          {decided[c.id] ? (
            <p className="meta" style={{ margin: 0 }}>{decided[c.id]}</p>
          ) : (
            <div className="btn-row">
              <button className="primary" onClick={() => void decide(c, "accept")}>採用</button>
              <button onClick={() => void decide(c, "once")}>今回だけ</button>
              <button onClick={() => void decide(c, "reject")}>違う</button>
            </div>
          )}
        </article>
      ))}

      {adopted.length ? (
        <section className="glass left-card">
          <div className="eyebrow">あなたの判断で変わったこと</div>
          {adopted.map((a) => (
            <div key={a.decisionId} className="adopted">
              <span>{a.ruleId ? <code>{a.ruleId}</code> : <span className="pill">反映待ち</span>} {a.text}</span>
              {a.reverted ? <span className="meta">取り消し済み</span> : a.ruleId ? <button onClick={() => void revert(a)}>取り消す</button> : null}
            </div>
          ))}
        </section>
      ) : null}
    </div>
  );
}
