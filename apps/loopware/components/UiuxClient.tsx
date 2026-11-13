"use client";

import { useEffect, useMemo, useState } from "react";
import { UIUX_PLAN_REASON_TAGS, UIUX_RULE_REASON_TAGS } from "@/lib/decisionContract";
import { UIUX_APP_LABEL, pickComplete, type PlanVerdict, type UiuxApp, type UiuxRound, type UiuxRule } from "@/lib/uiuxCore";
import LogJar, { type Bead } from "./LogJar";

/**
 * 画面の好み（ループウェア）。
 * 作る前：エージェントが好み帳を読んで置いた画面の案を、案ごとに 良い／違う／迷う＋理由タグ（任意）で判断し、1つ選ぶ。
 *        どれも違うときは選ばずに送れる（「どれも違う」も記録に残す）。
 * 土曜：作った後の直しからまとめた好みルール案を 採用／今回だけ／違う。採用したものだけが好み帳に入り、次の案づくりで読まれる。
 * AI はここでは呼ばない。
 */
function uid(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
  }
}

type Picked = { chosen: string | null; action: string; verdicts: Record<string, string>; at: string } | null;
type Recent = { works: number; firstOk: number; avgTrips: number | null };

const VERDICT_LABEL: Record<PlanVerdict, string> = { good: "良い", wrong: "違う", hesitated: "迷う" };
const RULE_LABEL: Record<string, string> = {
  rule_accept: "採用（好み帳へ）",
  rule_once: "今回だけ",
  rule_reject: "違う",
  rule_revert: "取り消し",
};
const BEAD_OF: Record<PlanVerdict, Bead> = { good: "take", wrong: "ng", hesitated: "hesitate" };

function appLabel(a: string | undefined): string {
  return a && a in UIUX_APP_LABEL ? UIUX_APP_LABEL[a as UiuxApp] : "3アプリ共通";
}

export default function UiuxClient() {
  const [round, setRound] = useState<UiuxRound | null | undefined>(undefined);
  const [rules, setRules] = useState<UiuxRule[]>([]);
  const [decided, setDecided] = useState<Record<string, string>>({});
  const [picked, setPicked] = useState<Picked>(null);
  const [recent, setRecent] = useState<Recent>({ works: 0, firstOk: 0, avgTrips: null });
  const [persisted, setPersisted] = useState(true);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [beads, setBeads] = useState<Bead[]>([]);

  const [chosen, setChosen] = useState<string | null>(null);
  const [verdicts, setVerdicts] = useState<Record<string, PlanVerdict>>({});
  const [tags, setTags] = useState<Record<string, string[]>>({});
  const [note, setNote] = useState("");
  const [redo, setRedo] = useState(false);
  const [ruleTags, setRuleTags] = useState<Record<string, string[]>>({});

  useEffect(() => {
    fetch("/api/uiux", { cache: "no-store" })
      .then((r) => r.json())
      .then((j) => {
        if (!j.ok) throw new Error(j.error || "読めませんでした");
        setPersisted(Boolean(j.persisted));
        setRound(j.round || null);
        setRules(j.rules || []);
        setDecided(j.decided || {});
        setPicked(j.picked || null);
        if (j.recent) setRecent(j.recent);
      })
      .catch((e) => {
        setMsg(e instanceof Error ? e.message : String(e));
        setRound(null);
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
      const r = await fetch("/api/uiux/decide", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...body, idemKey: `lw-uiux-${uid()}` }),
      });
      const j = await r.json().catch(() => ({}));
      if (!j.ok) {
        setMsg(j.error === "round_changed" ? "案が新しくなっています。開き直してください" : j.error || "記録できませんでした");
        return false;
      }
      setMsg("");
      return true;
    } finally {
      setBusy(false);
    }
  }

  function setVerdict(pid: string, v: PlanVerdict) {
    setVerdicts((x) => ({ ...x, [pid]: v }));
    if (v !== "good" && chosen === pid) setChosen(null);
  }

  function choose(pid: string) {
    setChosen(pid);
    setVerdicts((x) => ({ ...x, [pid]: "good" }));
  }

  function toggle(list: string[] | undefined, t: string): string[] {
    const xs = list || [];
    return xs.includes(t) ? xs.filter((x) => x !== t) : [...xs, t];
  }

  async function submitPick() {
    if (!round) return;
    const ok = await send({ kind: "plan", roundId: round.id, chosen, verdicts, tags, note: note.trim() || undefined });
    if (ok) {
      setPicked({ chosen, action: chosen ? "adopt" : "reject", verdicts, at: new Date().toISOString() });
      setBeads((b) => [...b, ...round.plans.map((p) => (verdicts[p.id] ? BEAD_OF[verdicts[p.id]] : "none"))]);
      setRedo(false);
    }
  }

  async function decideRule(pid: string, verdict: "accept" | "once" | "reject") {
    if (!round) return;
    if (await send({ kind: "rule", roundId: round.id, proposalId: pid, verdict, tags: ruleTags[pid] || [] })) {
      setDecided((d) => ({ ...d, [pid]: `rule_${verdict}` }));
      setBeads((b) => [...b, verdict === "accept" ? "take" : verdict === "once" ? "later" : "ng"]);
      const k = `${round.id}:${pid}`;
      if (verdict === "accept") {
        const p = round.proposals.find((x) => x.id === pid);
        if (p) setRules((rs) => [{ key: k, roundId: round.id, text: p.text, concept: p.concept || null, app: p.app || "*", at: new Date().toISOString() }, ...rs.filter((r) => r.key !== k)]);
      } else {
        setRules((rs) => rs.filter((r) => r.key !== k));
      }
    }
  }

  async function revert(r: UiuxRule) {
    if (await send({ kind: "rule", verdict: "revert", ruleKey: r.key, text: r.text })) {
      setRules((rs) => rs.filter((x) => x.key !== r.key));
      if (round && r.roundId === round.id) setDecided((d) => ({ ...d, [r.key.split(":")[1]]: "rule_revert" }));
    }
  }

  if (round === undefined) return <p className="meta">読み込み中…</p>;

  const showPlan = round && round.stage === "plan" && round.plans.length > 0 && (!picked || redo);
  const open = round ? round.proposals.filter((p) => !decided[p.id]).length : 0;
  const canSend = round ? pickComplete(round, { chosen, verdicts, tags }) : false;
  const okRate = recent.works ? Math.round((recent.firstOk / recent.works) * 100) : null;

  return (
    <div className="desk">
      <header>
        <div className="eyebrow acc">
          画面の好み{round ? `・${appLabel(round.app)}${round.screen ? `／${round.screen}` : ""}` : ""}
        </div>
        <strong className="desk-count">{round ? round.title : "案はまだありません"}</strong>
      </header>
      {!persisted ? <p className="meta">共有DBにつながっていません（見るだけ）。</p> : null}
      {msg ? <p className="meta" style={{ color: "var(--alert)" }}>{msg}</p> : null}
      {round?.note ? <p className="meta">{round.note}</p> : null}

      <section className="glass left-card">
        <div className="eyebrow">擦り合わせは減っているか（直近90日）</div>
        <p className="meta" style={{ margin: 0 }}>
          {recent.works
            ? `画面づくり ${recent.works} 件のうち 1案目でOK ${recent.firstOk} 件（${okRate}%）・平均 ${recent.avgTrips ?? "-"} 往復`
            : "まだ記録がありません。画面を作るたびに、AIが「1案目でOKだったか・何往復したか」を残します。"}
        </p>
        <p className="meta" style={{ margin: 0 }}>目標：1案目OK率 3か月後 50%・1年後 70%</p>
      </section>

      {beads.length ? <LogJar week={null} session={beads} /> : null}

      {!round ? (
        <div className="glass desk-empty">
          <p className="desk-empty-title">画面を変えるときに、AIがここへ案を置きます</p>
          <p className="meta">案は下の「好み帳」を読んでから作ります。判断した内容は次の案づくりに効きます。</p>
        </div>
      ) : null}

      {/* ---- 作る前：選んだ結果 ---- */}
      {round && round.stage === "plan" && picked && !redo ? (
        <section className="glass left-card">
          <div className="eyebrow">選んだ内容</div>
          <div className="left-subject">{picked.chosen ? round.plans.find((p) => p.id === picked.chosen)?.label || picked.chosen : "どれも違う"}</div>
          <p className="meta" style={{ margin: 0 }}>
            {round.plans.map((p) => `${p.label}：${VERDICT_LABEL[picked.verdicts[p.id] as PlanVerdict] || "—"}`).join("　")}
          </p>
          <p className="meta" style={{ margin: 0 }}>AIがこの判断を踏まえて作ります。作った後の「ここ違う」「これいいね」はチャットで話せば記録されます。</p>
          <div className="btn-row">
            <button onClick={() => setRedo(true)}>選び直す</button>
          </div>
        </section>
      ) : null}

      {/* ---- 作る前：案を判断 ---- */}
      {showPlan ? (
        <>
          <div className="eyebrow">画面の案（案ごとに 良い／違う／迷う。理由は任意）</div>
          {round!.plans.map((p) => {
            const on = chosen === p.id;
            const v = verdicts[p.id];
            return (
              <article key={p.id} className="glass left-card" style={chosen && !on ? { opacity: 0.8 } : undefined}>
                <div className="left-subject">
                  案{p.id}：{p.label}
                </div>
                {p.image ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <a href={p.image} target="_blank" rel="noreferrer">
                    <img src={p.image} alt={`案${p.id}の画面`} style={{ width: "100%", borderRadius: 12, border: "1px solid var(--line, rgba(0,0,0,.1))" }} />
                  </a>
                ) : null}
                <p className="meta" style={{ margin: 0 }}>{p.summary}</p>
                {p.points.length ? (
                  <ul className="meta" style={{ margin: 0, paddingLeft: 20 }}>
                    {p.points.map((o, i) => (
                      <li key={i}>{o}</li>
                    ))}
                  </ul>
                ) : null}
                {p.applied.length ? <p className="meta" style={{ margin: 0 }}>使った好み：{p.applied.map((k) => ruleText[k] || k).join("／")}</p> : null}
                <div className="btn-row">
                  {(["good", "wrong", "hesitated"] as PlanVerdict[]).map((x) => (
                    <button key={x} className={v === x ? "primary" : undefined} aria-pressed={v === x} onClick={() => setVerdict(p.id, x)}>
                      {VERDICT_LABEL[x]}
                    </button>
                  ))}
                  <button className={`tag${on ? " on" : ""}`} aria-pressed={on} onClick={() => choose(p.id)}>
                    {on ? "✓ この案で作る" : "この案で作る"}
                  </button>
                </div>
                {v ? (
                  <div className="tags" aria-label="理由（任意）">
                    {Object.entries(UIUX_PLAN_REASON_TAGS).map(([k, label]) => (
                      <button key={k} className={`tag${tags[p.id]?.includes(k) ? " on" : ""}`} onClick={() => setTags((s) => ({ ...s, [p.id]: toggle(s[p.id], k) }))}>
                        {label}
                      </button>
                    ))}
                  </div>
                ) : null}
              </article>
            );
          })}
          <section className="glass left-card">
            <label className="meta" htmlFor="uiux-note">ひとこと（任意・80字まで）</label>
            <input id="uiux-note" type="text" maxLength={80} value={note} onChange={(e) => setNote(e.target.value)} placeholder="例：Bの配置でAの色がいい" />
            <div className="btn-row">
              <button className="primary" disabled={busy || !canSend} onClick={() => void submitPick()}>
                {chosen ? "この内容で作ってもらう" : "どれも違う（作り直してもらう）"}
              </button>
              {redo ? <button onClick={() => setRedo(false)}>やめる</button> : null}
            </div>
            {!canSend ? <p className="meta" style={{ margin: 0 }}>案を1つ選ぶか、全部の案に「違う／迷う」を付けると送れます。</p> : null}
          </section>
        </>
      ) : null}

      {/* ---- 土曜：好みルール案 ---- */}
      {round && round.proposals.length ? (
        <>
          <div className="eyebrow">好みルール案（残り {open} 件）</div>
          <p className="meta">直しからAIがまとめた仮説です。採用したものだけが好み帳に入り、次の画面づくりで必ず読まれます。</p>
          {round.proposals.map((p) => {
            const d = decided[p.id];
            return (
              <article key={p.id} className="glass left-card" style={d ? { opacity: 0.6 } : undefined}>
                <div className="tags">
                  {p.concept ? <span className="pill">{p.concept}</span> : null}
                  <span className="pill">{appLabel(p.app)}</span>
                </div>
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
                  <p className="meta" style={{ margin: 0 }}>{RULE_LABEL[d] || d}</p>
                ) : (
                  <>
                    <div className="tags" aria-label="今回だけ・違うの理由（任意）">
                      {Object.entries(UIUX_RULE_REASON_TAGS).map(([k, label]) => (
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

      {/* ---- 好み帳 ---- */}
      <section className="glass left-card">
        <div className="eyebrow">好み帳（採用した好み {rules.length} 件）</div>
        {!rules.length ? <p className="meta" style={{ margin: 0 }}>まだありません。好みルール案で「採用」したものがここに並び、次の画面づくりに使われます。</p> : null}
        {rules.map((r) => (
          <div key={r.key} className="adopted">
            <span>
              {r.concept ? <span className="pill">{r.concept}</span> : null} {r.text}
              {r.app !== "*" ? <span className="meta">（{appLabel(r.app)}）</span> : null}
            </span>
            <button disabled={busy} onClick={() => void revert(r)}>取り消す</button>
          </div>
        ))}
      </section>
    </div>
  );
}
