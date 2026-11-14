"use client";

import { useEffect, useMemo, useState } from "react";
import { SLIDE_PLAN_REASON_TAGS, SLIDE_RULE_REASON_TAGS } from "@/lib/decisionContract";
import { logged } from "@/lib/logPulse";
import { planComplete, type SlideDeck, type SlideRule } from "@/lib/slidesCore";

/**
 * 資料づくり（ループウェア）。
 * 作る前：エージェントが置いた構成案から1つ選び、観点を選択肢で選ぶ（S03・S05）。選ばなかった案には理由タグを1タップ（T02）。
 * 振り返り：直しを概念にまとめた次回反映案を 採用／今回だけ／違う（L01・L03。分析は仮説、採否は本人）。
 * 採用したものだけが「資料の基準」になり、次回の案づくりに使われる。AI はここでは呼ばない。
 */
function uid(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }
}

type Planned = { plan: string | null; axes: Record<string, string>; at: string } | null;

const VERDICT_LABEL: Record<string, string> = {
  rule_accept: "採用（次回から使う）",
  rule_once: "今回だけ",
  rule_reject: "違う",
  rule_revert: "取り消し",
};

export default function SlidesClient() {
  const [deck, setDeck] = useState<SlideDeck | null | undefined>(undefined);
  const [rules, setRules] = useState<SlideRule[]>([]);
  const [decided, setDecided] = useState<Record<string, string>>({});
  const [planned, setPlanned] = useState<Planned>(null);
  const [persisted, setPersisted] = useState(true);
  const [msg, setMsg] = useState("");

  // 作る前の選択
  const [plan, setPlan] = useState<string | null>(null);
  const [axes, setAxes] = useState<Record<string, number>>({});
  const [skipTags, setSkipTags] = useState<Record<string, string[]>>({});
  const [note, setNote] = useState("");
  const [redo, setRedo] = useState(false);
  const [busy, setBusy] = useState(false);

  // 振り返り：反映案ごとの理由タグ
  const [ruleTags, setRuleTags] = useState<Record<string, string[]>>({});

  useEffect(() => {
    fetch("/api/slides", { cache: "no-store" })
      .then((r) => r.json())
      .then((j) => {
        if (!j.ok) throw new Error(j.error || "読めませんでした");
        setPersisted(Boolean(j.persisted));
        setDeck(j.deck || null);
        setRules(j.rules || []);
        setDecided(j.decided || {});
        setPlanned(j.planned || null);
        const d = j.deck as SlideDeck | null;
        if (d) {
          const init: Record<string, number> = {};
          for (const a of d.axes) if (a.recommended !== undefined) init[a.key] = a.recommended;
          setAxes(init);
        }
      })
      .catch((e) => {
        setMsg(e instanceof Error ? e.message : String(e));
        setDeck(null);
      });
  }, []);

  const ruleText = useMemo(() => {
    const m: Record<string, string> = {};
    for (const r of rules) m[r.key] = r.text;
    return m;
  }, [rules]);

  async function send(body: Record<string, unknown>): Promise<boolean> {
    setBusy(true);
    try {
      const r = await fetch("/api/slides/decide", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...body, idemKey: `lw-slide-${uid()}` }),
      });
      const j = await r.json().catch(() => ({}));
      if (!j.ok) {
        setMsg(j.error === "deck_changed" ? "資料の案が新しくなっています。開き直してください" : j.error || "記録できませんでした");
        return false;
      }
      if (j.persisted === false) setMsg("共有DBに保存できませんでした（端末にも残していません）。");
      return true;
    } finally {
      setBusy(false);
    }
  }

  async function submitPlan() {
    if (!deck) return;
    const notChosen = Object.entries(skipTags).map(([p, tags]) => ({ plan: p, tags }));
    const ok = await send({ kind: "plan", deckId: deck.id, plan, axes, notChosen, note: note.trim() || undefined });
    if (ok) {
      const ax: Record<string, string> = {};
      for (const a of deck.axes) ax[a.key] = a.options[axes[a.key]];
      setPlanned({ plan, axes: ax, at: new Date().toISOString() });
      setRedo(false);
      setMsg("");
      logged({ beads: ["take", ...notChosen.map(() => "ng" as const)], label: "資料の構成を決めました", big: true });
    }
  }

  async function decideRule(pid: string, verdict: "accept" | "once" | "reject") {
    if (!deck) return;
    if (await send({ kind: "rule", deckId: deck.id, proposalId: pid, verdict, tags: ruleTags[pid] || [] })) {
      setDecided((d) => ({ ...d, [pid]: `rule_${verdict}` }));
      const rest = deck.proposals.filter((p) => p.id !== pid && !decided[p.id]).length;
      logged({
        beads: [verdict === "accept" ? "take" : verdict === "once" ? "later" : "ng"],
        label: rest ? VERDICT_LABEL[`rule_${verdict}`] : "反映案をすべて判断しました",
        big: rest === 0,
      });
      if (verdict === "accept") {
        const p = deck.proposals.find((x) => x.id === pid);
        if (p) setRules((rs) => [{ key: `${deck.id}:${pid}`, deckId: deck.id, text: p.text, concept: p.concept || null, at: new Date().toISOString(), reverted: false }, ...rs.filter((r) => r.key !== `${deck.id}:${pid}`)]);
      } else {
        setRules((rs) => rs.filter((r) => r.key !== `${deck.id}:${pid}`));
      }
    }
  }

  async function revert(r: SlideRule) {
    if (await send({ kind: "rule", verdict: "revert", ruleKey: r.key, text: r.text })) {
      setRules((rs) => rs.filter((x) => x.key !== r.key));
      logged({ beads: ["note"], label: "基準を取り消しました" });
      if (deck && r.deckId === deck.id) setDecided((d) => ({ ...d, [r.key.split(":")[1]]: "rule_revert" }));
    }
  }

  function toggle(list: string[] | undefined, t: string): string[] {
    const xs = list || [];
    return xs.includes(t) ? xs.filter((x) => x !== t) : [...xs, t];
  }

  if (deck === undefined) return <p className="meta">読み込み中…</p>;

  const showPlan = deck && deck.stage === "plan" && (!planned || redo);
  const open = deck ? deck.proposals.filter((p) => !decided[p.id]).length : 0;

  return (
    <div className="desk">
      <header>
        <div className="eyebrow acc">資料づくり{deck ? `・${deck.stage === "plan" ? "作る前" : deck.stage === "review" ? "振り返り" : "完了"}` : ""}</div>
        <strong className="desk-count">{deck ? deck.title : "案はまだありません"}</strong>
      </header>
      {!persisted ? <p className="meta">共有DBにつながっていません（見るだけ）。</p> : null}
      {msg ? <p className="meta" style={{ color: "var(--alert)" }}>{msg}</p> : null}
      {deck?.note ? <p className="meta">{deck.note}</p> : null}

      {!deck ? (
        <div className="glass desk-empty">
          <p className="desk-empty-title">エージェントに「資料の案を作って」と頼んでください</p>
          <p className="meta">Claude Code／Miss Lemon が、下の「資料の基準」を踏まえた構成案をここに置きます。</p>
        </div>
      ) : null}

      {/* ---- 作る前 ---- */}
      {deck && deck.stage === "plan" && planned && !redo ? (
        <section className="glass left-card">
          <div className="eyebrow">選んだ内容</div>
          <div className="left-subject">{deck.plans.find((p) => p.id === planned.plan)?.label || "（案なし）"}</div>
          <p className="meta" style={{ margin: 0 }}>{Object.entries(planned.axes).map(([k, v]) => `${deck.axes.find((a) => a.key === k)?.label || k}：${v}`).join("　")}</p>
          <p className="meta" style={{ margin: 0 }}>エージェントがこの内容で資料を作ります。直し終わったら「直した内容で振り返りを作って」と頼んでください。</p>
          <div className="btn-row">
            <button onClick={() => setRedo(true)}>選び直す</button>
          </div>
        </section>
      ) : null}

      {showPlan ? (
        <>
          <div className="eyebrow">構成案（1つ選ぶ）</div>
          {deck!.plans.map((p) => {
            const on = plan === p.id;
            return (
              <article key={p.id} className="glass left-card" style={plan && !on ? { opacity: 0.75 } : undefined}>
                <button className={`tag${on ? " on" : ""}`} style={{ alignSelf: "flex-start" }} onClick={() => setPlan(p.id)} aria-pressed={on}>
                  {on ? "✓ この案にする" : `案${p.id}：${p.label}`}
                </button>
                <div className="left-subject">{p.label}</div>
                <p className="meta" style={{ margin: 0 }}>{p.summary}</p>
                {p.outline.length ? (
                  <ol className="meta" style={{ margin: "4px 0 0", paddingLeft: 20 }}>
                    {p.outline.map((o, i) => (
                      <li key={i}>{o}</li>
                    ))}
                  </ol>
                ) : null}
                {p.applied.length ? (
                  <p className="meta" style={{ margin: 0 }}>
                    前回の学びを反映：{p.applied.map((k) => ruleText[k] || k).join("／")}
                  </p>
                ) : null}
                {plan && !on ? (
                  <div className="tags" aria-label="選ばなかった理由（任意）">
                    {Object.entries(SLIDE_PLAN_REASON_TAGS).map(([k, label]) => (
                      <button key={k} className={`tag${skipTags[p.id]?.includes(k) ? " on" : ""}`} onClick={() => setSkipTags((s) => ({ ...s, [p.id]: toggle(s[p.id], k) }))}>
                        {label}
                      </button>
                    ))}
                  </div>
                ) : null}
              </article>
            );
          })}

          <div className="eyebrow">観点（★は推し）</div>
          {deck!.axes.map((a) => (
            <section key={a.key} className="glass left-card">
              <strong>{a.label}</strong>
              <div className="tags">
                {a.options.map((o, i) => (
                  <button key={o} className={`tag${axes[a.key] === i ? " on" : ""}`} onClick={() => setAxes((x) => ({ ...x, [a.key]: i }))}>
                    {a.recommended === i ? "★ " : ""}
                    {o}
                  </button>
                ))}
              </div>
            </section>
          ))}

          <section className="glass left-card">
            <label className="meta" htmlFor="slide-note">ひとこと（任意・60字まで）</label>
            <input id="slide-note" type="text" maxLength={60} value={note} onChange={(e) => setNote(e.target.value)} placeholder="例：今回は事例を1つ多めに" />
            <div className="btn-row">
              <button className="primary" disabled={busy || !planComplete(deck!, { plan, axes })} onClick={() => void submitPlan()}>
                この内容で作ってもらう
              </button>
              {redo ? <button onClick={() => setRedo(false)}>やめる</button> : null}
            </div>
          </section>
        </>
      ) : null}

      {/* ---- 振り返り ---- */}
      {deck && deck.stage !== "plan" ? (
        <>
          <div className="eyebrow">次回への反映案（残り {open} 件）</div>
          <p className="meta">今回の直しから、エージェントがまとめた仮説です。採用したものだけが次回の案づくりに効きます。</p>
          {!deck.proposals.length ? <p className="meta">反映案はまだありません。</p> : null}
          {deck.proposals.map((p) => {
            const d = decided[p.id];
            return (
              <article key={p.id} className="glass left-card" style={d ? { opacity: 0.6 } : undefined}>
                {p.concept ? <span className="pill" style={{ alignSelf: "flex-start" }}>{p.concept}</span> : null}
                <div className="left-subject">{p.text}</div>
                <p className="meta" style={{ margin: 0 }}>根拠：{p.why}</p>
                {p.evidence?.length ? (
                  <ul className="meta" style={{ margin: 0, paddingLeft: 20 }}>
                    {p.evidence.map((e, i) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                ) : null}
                {d ? (
                  <p className="meta" style={{ margin: 0 }}>{VERDICT_LABEL[d] || d}</p>
                ) : (
                  <>
                    <div className="tags" aria-label="今回だけ・違うの理由（任意）">
                      {Object.entries(SLIDE_RULE_REASON_TAGS).map(([k, label]) => (
                        <button key={k} className={`tag${ruleTags[p.id]?.includes(k) ? " on" : ""}`} onClick={() => setRuleTags((s) => ({ ...s, [p.id]: toggle(s[p.id], k) }))}>
                          {label}
                        </button>
                      ))}
                    </div>
                    <div className="btn-row">
                      <button className="primary" disabled={busy} onClick={() => void decideRule(p.id, "accept")}>採用</button>
                      <button disabled={busy} onClick={() => void decideRule(p.id, "once")}>今回だけ</button>
                      <button disabled={busy} onClick={() => void decideRule(p.id, "reject")}>違う</button>
                    </div>
                  </>
                )}
              </article>
            );
          })}
        </>
      ) : null}

      {/* ---- 資料の基準 ---- */}
      <section className="glass left-card">
        <div className="eyebrow">資料の基準（採用した学び {rules.length} 件）</div>
        {!rules.length ? <p className="meta" style={{ margin: 0 }}>まだありません。振り返りで「採用」したものがここに並び、次回の案づくりに使われます。</p> : null}
        {rules.map((r) => (
          <div key={r.key} className="adopted">
            <span>
              {r.concept ? <span className="pill">{r.concept}</span> : null} {r.text}
            </span>
            <button disabled={busy} onClick={() => void revert(r)}>取り消す</button>
          </div>
        ))}
      </section>
    </div>
  );
}
