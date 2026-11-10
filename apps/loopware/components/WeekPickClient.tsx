"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Icon from "./Icon";
import {
  LEFT_REASONS,
  NEXT_STEPS,
  PICK_REASONS,
  buildDecisions,
  buildPlan,
  dayCounts,
  dayLabel,
  eventsByDay,
  initialState,
  shortTitle,
  threeWeeks,
  weekday,
  type Calendar,
  type Candidate,
  type InletCandidate,
  type NextStep,
  type Snapshot,
  type WeekState,
} from "@/lib/weekPick";

type Status = { commit: { id: number; decided_at: string } | null; applied: { decided_at: string; result: unknown } | null };
type Step = 1 | 2 | 3;

const WD = ["日", "月", "火", "水", "木", "金", "土"];

function draftKey(week: string) {
  return `weekpick:v1:${week}`;
}
function loadDraft(week: string): WeekState | null {
  try {
    const raw = localStorage.getItem(draftKey(week));
    return raw ? (JSON.parse(raw) as WeekState) : null;
  } catch {
    return null;
  }
}
function saveDraft(week: string, st: WeekState) {
  try {
    localStorage.setItem(draftKey(week), JSON.stringify(st));
  } catch {
    /* 端末の保存が使えないときは何もしない */
  }
}
/** JST で "11/15 16:30" */
function hhmm(iso: string) {
  const d = new Date(new Date(iso).getTime() + 9 * 3600_000);
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()} ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}

export default function WeekPickClient() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [cal, setCal] = useState<Calendar | null>(null);
  const [status, setStatus] = useState<Status>({ commit: null, applied: null });
  const [st, setSt] = useState<WeekState | null>(null);
  const [step, setStep] = useState<Step>(1);
  const [sel, setSel] = useState<string | null>(null); // カレンダーに置く候補
  const [showAll, setShowAll] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState("");
  const [recommit, setRecommit] = useState(false);

  useEffect(() => {
    fetch("/api/week", { cache: "no-store" })
      .then((r) => r.json())
      .then((j) => {
        if (!j.ok) throw new Error(j.error || "読み込めませんでした");
        setSnap(j.snapshot);
        setCal(j.calendar);
        setStatus({ commit: j.commit, applied: j.applied });
        if (j.snapshot) {
          const s = j.snapshot as Snapshot;
          setSt(loadDraft(s.week) || initialState(s));
          if (!Object.keys(initialState(s).left).length) setStep(2);
        }
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  const update = useCallback(
    (fn: (s: WeekState) => WeekState) => {
      setSt((prev) => {
        if (!prev || !snap) return prev;
        const next = fn(structuredClone(prev));
        saveDraft(snap.week, next);
        return next;
      });
    },
    [snap],
  );

  const flash = (m: string) => {
    setToast(m);
    window.setTimeout(() => setToast(""), 1800);
  };

  if (loading) return <div className="glass" style={{ padding: 20 }}><span className="meta">今週の材料を読み込んでいます…</span></div>;
  if (err) return <div className="warn">読み込めませんでした: {err}</div>;
  if (!snap || !st) {
    return (
      <div className="glass wk-empty">
        <Icon name="calendar" size={28} />
        <strong>まだ今週の材料がありません</strong>
        <p className="meta">日曜 17:00 に先週の結果とおすすめ9件が届きます。急ぐときは GitHub Actions の「今週の9件」を手動で動かしてください。</p>
      </div>
    );
  }

  const s = snap;
  const byId = new Map(s.candidates.map((c) => [c.id, c]));
  const counts = dayCounts(s, st);
  const placed = Object.values(counts).reduce((a, b) => a + b, 0);
  const cap = s.per_day * s.days.length;
  const leftIds = Object.keys(st.left);
  const leftDone = leftIds.filter((id) => st.left[id].tags.length || st.left[id].next !== "keep").length;
  const committedThisWeek = !!status.commit && !recommit;

  function place(id: string, day: string | null) {
    update((x) => {
      if (id.startsWith("inlet:")) {
        const tid = id.slice(6);
        x.inlet[tid] = day ? { action: "week", day } : { action: "keep" };
      } else {
        x.slots[id] = day;
      }
      return x;
    });
    setSel(null);
    if (day) flash(`${dayLabel(day)} に置きました`);
  }

  function dayFull(day: string) {
    return (counts[day] || 0) >= s.per_day;
  }

  async function commit() {
    if (!st) return;
    setSaving(true);
    try {
      const plan = buildPlan(s, st);
      const nonce = `${Date.now().toString(36)}`;
      const rows = buildDecisions(s, st, plan, nonce, new Date().toISOString());
      const r = await fetch("/api/week", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ decisions: rows }) });
      const j = await r.json();
      if (!j.ok) throw new Error(j.reason || j.error || "保存できませんでした");
      setStatus({ commit: { id: 0, decided_at: new Date().toISOString() }, applied: null });
      setRecommit(false);
      flash(`確定しました（判断 ${j.saved + 1} 件を記録）`);
    } catch (e) {
      flash(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="wk">
      {toast && <div className="desk-toast">{toast}</div>}

      <div className="wk-head glass">
        <div>
          <div className="eyebrow">{dayLabel(s.days[0])} からの1週間</div>
          <div className="wk-progress">
            <b>{placed}</b>
            <span>/ {cap} 件を置いた</span>
          </div>
        </div>
        <div className="wk-dots" aria-label="曜日ごとの枠">
          {s.days.map((d) => (
            <div key={d} className={`wk-dot ${counts[d] >= s.per_day ? "full" : ""}`}>
              <span>{WD[weekday(d)]}</span>
              <b>{counts[d]}/{s.per_day}</b>
            </div>
          ))}
        </div>
      </div>

      {status.commit && (
        <div className={`wk-banner ${status.applied ? "ok" : ""}`}>
          <Icon name={status.applied ? "check" : "clock"} size={18} />
          <span>
            {hhmm(status.commit.decided_at)} に確定。
            {status.applied ? `Todoist へ反映済み（${hhmm(status.applied.decided_at)}）` : "Todoist には30分以内に反映されます"}
          </span>
          {!recommit && (
            <button className="wk-link" onClick={() => setRecommit(true)}>
              確定し直す
            </button>
          )}
        </div>
      )}

      <nav className="wk-steps" aria-label="手順">
        {([
          [1, "振り返る", leftIds.length ? `${leftDone}/${leftIds.length}` : "なし"],
          [2, "選んで置く", `${placed}/${cap}`],
          [3, "確定", committedThisWeek ? "済" : ""],
        ] as [Step, string, string][]).map(([n, label, sub]) => (
          <button key={n} className={`wk-step ${step === n ? "on" : ""}`} onClick={() => setStep(n)}>
            <span className="n">{n}</span>
            <span className="l">{label}</span>
            {sub && <span className="s">{sub}</span>}
          </button>
        ))}
      </nav>

      {step === 1 && (
        <Review s={s} st={st} update={update} byId={byId} onNext={() => setStep(2)} />
      )}

      {step === 2 && (
        <div className="wk-board">
          <section className="wk-cal-col">
            <CalendarBoard
              s={s}
              cal={cal}
              st={st}
              byId={byId}
              sel={sel}
              onDayTap={(d) => {
                if (!sel) return;
                if (dayFull(d)) return flash(`${dayLabel(d)} はもう ${s.per_day} 件です`);
                place(sel, d);
              }}
              onChipTap={(id) => setSel(sel === id ? null : id)}
            />
          </section>
          <section className="wk-list-col">
            <PickList
              s={s}
              st={st}
              update={update}
              sel={sel}
              setSel={setSel}
              place={place}
              dayFull={dayFull}
              showAll={showAll}
              setShowAll={setShowAll}
            />
            <button className="cta" onClick={() => setStep(3)}>
              確定へ <Icon name="arrow" size={18} />
            </button>
          </section>
        </div>
      )}

      {step === 3 && (
        <Confirm s={s} st={st} update={update} byId={byId} saving={saving} locked={committedThisWeek} onCommit={commit} />
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- ① 振り返る */

function Review({
  s,
  st,
  update,
  byId,
  onNext,
}: {
  s: Snapshot;
  st: WeekState;
  update: (fn: (x: WeekState) => WeekState) => void;
  byId: Map<string, Candidate>;
  onNext: () => void;
}) {
  const [openDone, setOpenDone] = useState(false);
  const ids = Object.keys(st.left);
  return (
    <div className="wk-section">
      <div className="wk-stats">
        <div className="wk-stat good"><b>{s.last.done}</b><span>先週の完了</span></div>
        <div className="wk-stat warn"><b>{s.last.left}</b><span>残った</span></div>
        <div className="wk-stat"><b>{s.last.added}</b><span>追加された</span></div>
        <div className="wk-stat"><b>{s.last.owner_open}</b><span>松野さん対応の残り</span></div>
      </div>
      {s.last.done_titles.length > 0 && (
        <button className="wk-link" onClick={() => setOpenDone(!openDone)}>
          {openDone ? "完了したものを閉じる" : `完了したもの ${s.last.done} 件を見る`}
        </button>
      )}
      {openDone && (
        <ul className="wk-done">
          {s.last.done_titles.map((t, i) => (
            <li key={i}><Icon name="check" size={14} /> {t}</li>
          ))}
        </ul>
      )}

      <h2 className="wk-h">残ったもの <small>なぜ残ったか・次の手</small></h2>
      {!ids.length && <p className="meta">先週の残りはありません。</p>}
      {ids.map((id) => {
        const c = byId.get(id);
        const a = st.left[id];
        return (
          <article key={id} className="glass wk-card">
            <div className="wk-card-head">
              <strong>{c?.title || id}</strong>
              {c && c.weeks_carried > 0 && <span className="wk-badge warn">{c.weeks_carried}週残り</span>}
              {c?.due && <span className="wk-badge">{dayLabel(c.due)}</span>}
            </div>
            <div className="wk-chips">
              {Object.entries(LEFT_REASONS).map(([k, label]) => (
                <button
                  key={k}
                  className={`wk-chip ${a.tags.includes(k) ? "on" : ""}`}
                  onClick={() =>
                    update((x) => {
                      const t = x.left[id].tags;
                      x.left[id].tags = t.includes(k) ? t.filter((y) => y !== k) : [...t, k];
                      return x;
                    })
                  }
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="wk-seg" role="radiogroup" aria-label="次の手">
              {(Object.entries(NEXT_STEPS) as [NextStep, string][]).map(([k, label]) => (
                <button
                  key={k}
                  role="radio"
                  aria-checked={a.next === k}
                  className={`${a.next === k ? "on" : ""} ${k === "drop" ? "drop" : ""}`}
                  onClick={() =>
                    update((x) => {
                      x.left[id].next = k;
                      if (k !== "keep") x.slots[id] = null;
                      return x;
                    })
                  }
                >
                  {label}
                </button>
              ))}
            </div>
            <input
              type="text"
              value={a.note}
              placeholder="ひとこと（任意）"
              onChange={(e) => {
                const v = e.target.value;
                update((x) => {
                  x.left[id].note = v;
                  return x;
                });
              }}
            />
          </article>
        );
      })}
      <button className="cta" onClick={onNext}>
        次へ：9件を選んで置く <Icon name="arrow" size={18} />
      </button>
    </div>
  );
}

/* ---------------------------------------------------------------- ② カレンダー */

function CalendarBoard({
  s,
  cal,
  st,
  byId,
  sel,
  onDayTap,
  onChipTap,
}: {
  s: Snapshot;
  cal: Calendar | null;
  st: WeekState;
  byId: Map<string, Candidate>;
  sel: string | null;
  onDayTap: (d: string) => void;
  onChipTap: (id: string) => void;
}) {
  const weeks = threeWeeks(s.days[0]);
  const ev = eventsByDay(cal);
  const pickDays = new Set(s.days);
  const placedBy: Record<string, { id: string; title: string }[]> = {};
  for (const [id, d] of Object.entries(st.slots)) if (d) (placedBy[d] ||= []).push({ id, title: shortTitle(byId.get(id)?.title || id) });
  for (const c of s.inlet) {
    const v = st.inlet[c.id];
    if (v?.action === "week" && v.day) (placedBy[v.day] ||= []).push({ id: `inlet:${c.id}`, title: shortTitle(c.title) });
  }
  const hardBy: Record<string, string[]> = {};
  for (const c of s.candidates) {
    const lim = c.deadline || (c.hard ? c.due : null);
    if (lim) (hardBy[lim] ||= []).push(shortTitle(c.title));
  }
  for (const h of s.hard_ahead) if (!(hardBy[h.date] || []).includes(shortTitle(h.title))) (hardBy[h.date] ||= []).push(shortTitle(h.title));
  const today = new Date(Date.now() + 9 * 3600_000).toISOString().slice(0, 10);

  return (
    <div className="wk-cal glass">
      <div className="wk-cal-legend">
        <span><i className="lg pick" />置いたタスク</span>
        <span><i className="lg hard" />締切・支払い・行事</span>
        <span><i className="lg fam" />家族の予定（参考）</span>
      </div>
      {sel && <div className="wk-hint"><Icon name="calendar" size={16} /> 月・水・金のマスをタップして置く</div>}
      <div className="wk-cal-dow">
        {[1, 2, 3, 4, 5, 6, 0].map((d) => (
          <span key={d} className={d === 0 || d === 6 ? "we" : ""}>{WD[d]}</span>
        ))}
      </div>
      {weeks.map((days, wi) => (
        <div key={wi} className={`wk-week ${wi === 0 ? "now" : "ahead"}`}>
          <div className="wk-week-label">
            {wi === 0 ? "この週を決める" : wi === 1 ? "次の週（順番だけ・期日は入れない）" : "その次（締切・行事だけ見る）"}
          </div>
          <div className="wk-grid">
            {days.map((d) => {
              const isPick = wi === 0 && pickDays.has(d);
              const wd = weekday(d);
              const role = wi !== 0 ? "" : isPick ? "枠" : wd === 2 || wd === 4 ? "空け" : wd === 6 || wd === 0 ? "残り" : "";
              const events = ev[d] || [];
              const holiday = events.find((e) => e.kind === "holiday");
              return (
                <div
                  key={d}
                  className={`wk-day ${isPick ? "pick" : ""} ${isPick && sel ? "target" : ""} ${wd === 0 || wd === 6 || holiday ? "we" : ""} ${d === today ? "today" : ""}`}
                  onClick={() => isPick && onDayTap(d)}
                  role={isPick ? "button" : undefined}
                  aria-label={isPick ? `${dayLabel(d)} に置く` : undefined}
                >
                  <div className="wk-day-top">
                    <span className="dn">{Number(d.slice(8, 10))}</span>
                    {role && <span className={`role ${isPick ? "pick" : ""}`}>{role}</span>}
                  </div>
                  {holiday && <div className="wk-ev hol">{holiday.title}</div>}
                  {(hardBy[d] || []).map((t, i) => (
                    <div key={`h${i}`} className="wk-ev hard" title={t}>{t}</div>
                  ))}
                  {(placedBy[d] || []).map((p) => (
                    <button
                      key={p.id}
                      className={`wk-ev pick ${sel === p.id ? "sel" : ""}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onChipTap(p.id);
                      }}
                      title={p.title}
                    >
                      {p.title}
                    </button>
                  ))}
                  {events
                    .filter((e) => e.kind !== "holiday")
                    .slice(0, wi === 0 ? 4 : 3)
                    .map((e, i) => (
                      <div key={`e${i}`} className={`wk-ev ${e.kind === "family" ? "fam" : "evt"}`} title={`${e.start || "終日"} ${e.title}`}>
                        {e.start && <span className="t">{e.start}</span>}
                        {e.title}
                      </div>
                    ))}
                  {events.filter((e) => e.kind !== "holiday").length > (wi === 0 ? 4 : 3) && (
                    <div className="wk-more">+{events.filter((e) => e.kind !== "holiday").length - (wi === 0 ? 4 : 3)}</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}
      {!cal && <p className="meta wk-cal-note">カレンダーはまだ届いていません（Mac で毎朝 6:30・日曜 16:30 に取り込み）。</p>}
      {cal && <p className="meta wk-cal-note">カレンダー {hhmm(cal.generated_at)} 時点</p>}
    </div>
  );
}

/* ---------------------------------------------------------------- ② 候補 */

function PickList({
  s,
  st,
  update,
  sel,
  setSel,
  place,
  dayFull,
  showAll,
  setShowAll,
}: {
  s: Snapshot;
  st: WeekState;
  update: (fn: (x: WeekState) => WeekState) => void;
  sel: string | null;
  setSel: (id: string | null) => void;
  place: (id: string, day: string | null) => void;
  dayFull: (d: string) => boolean;
  showAll: boolean;
  setShowAll: (v: boolean) => void;
}) {
  const rec = new Map(s.recommended.map((r) => [r.id, r.day]));
  const placedIds = new Set(Object.entries(st.slots).filter(([, d]) => d).map(([id]) => id));
  const recList = s.candidates.filter((c) => rec.has(c.id));
  const others = s.candidates.filter((c) => !rec.has(c.id) && !(st.left[c.id] && st.left[c.id].next !== "keep"));
  const extraPlaced = others.filter((c) => placedIds.has(c.id));
  const rest = others.filter((c) => !placedIds.has(c.id));
  const nextRank = new Map(s.next_preview.map((id, i) => [id, i + 1]));
  const visibleRest = showAll ? rest : rest.slice(0, 10);

  return (
    <div className="wk-section">
      <h2 className="wk-h">
        おすすめ {recList.length} 件 <small>AI の案。理由を直して置き直せます</small>
      </h2>
      {recList.map((c) => (
        <PickCard key={c.id} c={c} s={s} st={st} update={update} sel={sel} setSel={setSel} place={place} dayFull={dayFull} aiDay={rec.get(c.id) || null} />
      ))}
      {extraPlaced.map((c) => (
        <PickCard key={c.id} c={c} s={s} st={st} update={update} sel={sel} setSel={setSel} place={place} dayFull={dayFull} aiDay={null} />
      ))}

      {s.inlet.length > 0 && (
        <>
          <h2 className="wk-h">
            入口で待っている話題 <small>入れる・今週やる・見送るをここで</small>
          </h2>
          {s.inlet.map((c) => (
            <InletCard key={c.id} c={c} s={s} st={st} update={update} place={place} dayFull={dayFull} />
          ))}
        </>
      )}

      <h2 className="wk-h">
        そのほかの候補 <small>{rest.length} 件・上ほど急ぎ</small>
      </h2>
      {visibleRest.map((c) => (
        <PickCard key={c.id} c={c} s={s} st={st} update={update} sel={sel} setSel={setSel} place={place} dayFull={dayFull} aiDay={null} compact nextRank={nextRank.get(c.id)} />
      ))}
      {rest.length > 10 && (
        <button className="secondary" onClick={() => setShowAll(!showAll)}>
          {showAll ? "たたむ" : `残り ${rest.length - 10} 件も見る`}
        </button>
      )}
    </div>
  );
}

function PickCard({
  c,
  s,
  st,
  update,
  sel,
  setSel,
  place,
  dayFull,
  aiDay,
  compact = false,
  nextRank,
}: {
  c: Candidate;
  s: Snapshot;
  st: WeekState;
  update: (fn: (x: WeekState) => WeekState) => void;
  sel: string | null;
  setSel: (id: string | null) => void;
  place: (id: string, day: string | null) => void;
  dayFull: (d: string) => boolean;
  aiDay: string | null;
  compact?: boolean;
  nextRank?: number;
}) {
  const day = st.slots[c.id] || null;
  const r = st.reasons[c.id] || { tags: [], text: "" };
  const moved = aiDay && day !== aiDay;
  const lim = c.deadline || (c.hard ? c.due : null);
  const aiTags = new Set(c.reasons.map((x) => x.tag));
  const [more, setMore] = useState(false);
  const extra = Object.entries(PICK_REASONS).filter(([k]) => !aiTags.has(k) && !["inlet", "carried", "planned"].includes(k));
  const extraOn = extra.filter(([k]) => r.tags.includes(k));

  function toggleReason(tag: string, text: string) {
    update((x) => {
      const cur = x.reasons[c.id] || { tags: [], text: "" };
      const on = cur.tags.includes(tag);
      const tags = on ? cur.tags.filter((t) => t !== tag) : [...cur.tags, tag];
      const texts = cur.text ? cur.text.split("／").filter(Boolean) : [];
      const nextTexts = on ? texts.filter((t) => t !== text) : [...texts, text];
      x.reasons[c.id] = { tags, text: nextTexts.join("／") };
      return x;
    });
  }

  return (
    <article className={`glass wk-card ${day ? "placed" : ""} ${sel === c.id ? "sel" : ""} ${compact && !day ? "compact" : ""}`}>
      <div className="wk-card-head">
        <button className="wk-title" onClick={() => setSel(sel === c.id ? null : c.id)} aria-pressed={sel === c.id}>
          {c.mark === "requested" && <span className="wk-mark">🦾依頼</span>}
          {c.mark === "ai" && <span className="wk-mark">🤖</span>}
          {c.title}
        </button>
        <a className="wk-open" href={c.url} target="_blank" rel="noreferrer" aria-label="Todoist で開く">
          <Icon name="next" size={16} />
        </a>
      </div>
      <div className="wk-meta">
        {c.priority !== "p4" && <span className={`wk-badge ${c.priority}`}>{c.priority}</span>}
        {lim && <span className="wk-badge hard">締切 {dayLabel(lim)}</span>}
        {!lim && c.due && <span className="wk-badge">期日 {dayLabel(c.due)}</span>}
        {c.weeks_carried > 0 && <span className="wk-badge warn">{c.weeks_carried}週目</span>}
        {aiDay && <span className="wk-badge ai">AI案 {dayLabel(aiDay)}</span>}
        {moved && <span className="wk-badge moved">{day ? "AI案から移した" : "AI案を外した"}</span>}
        {nextRank && <span className="wk-badge">次週候補 {nextRank}位</span>}
      </div>

      <div className="wk-days">
        {s.days.map((d) => (
          <button
            key={d}
            className={`wk-daybtn ${day === d ? "on" : ""}`}
            disabled={day !== d && dayFull(d)}
            onClick={() => place(c.id, day === d ? null : d)}
          >
            {WD[weekday(d)]}
          </button>
        ))}
        {day && (
          <button className="wk-daybtn off" onClick={() => place(c.id, null)} aria-label="置くのをやめる">
            <Icon name="x" size={14} />
          </button>
        )}
      </div>

      {(day || !compact) && (
        <div className="wk-reason">
          <div className="wk-reason-label">選ぶ理由</div>
          <div className="wk-chips">
            {c.reasons.map((x) => (
              <button key={x.tag} className={`wk-chip ai ${r.tags.includes(x.tag) ? "on" : ""}`} onClick={() => toggleReason(x.tag, x.text)}>
                {x.text}
              </button>
            ))}
            {(more ? extra : extraOn).map(([k, label]) => (
              <button key={k} className={`wk-chip ${r.tags.includes(k) ? "on" : ""}`} onClick={() => toggleReason(k, label)}>
                {label}
              </button>
            ))}
            {!more && (
              <button className="wk-chip add" onClick={() => setMore(true)} aria-label="理由を足す">
                ＋ 理由を足す
              </button>
            )}
          </div>
          {day && (
            <input
              type="text"
              value={r.text}
              placeholder="理由を自分のことばで（任意）"
              onChange={(e) => {
                const v = e.target.value;
                update((x) => {
                  x.reasons[c.id] = { ...(x.reasons[c.id] || { tags: [] }), text: v };
                  return x;
                });
              }}
            />
          )}
        </div>
      )}
    </article>
  );
}

function InletCard({
  c,
  s,
  st,
  update,
  place,
  dayFull,
}: {
  c: InletCandidate;
  s: Snapshot;
  st: WeekState;
  update: (fn: (x: WeekState) => WeekState) => void;
  place: (id: string, day: string | null) => void;
  dayFull: (d: string) => boolean;
}) {
  const v = st.inlet[c.id];
  return (
    <article className={`glass wk-card inlet ${v ? "placed" : ""}`}>
      <div className="wk-card-head">
        <strong>{c.title}</strong>
        <span className="wk-badge warn">入口 {c.waited_days}日</span>
      </div>
      {c.body && c.body !== c.title && <p className="meta wk-body">{c.body}</p>}
      <div className="wk-days">
        {s.days.map((d) => (
          <button
            key={d}
            className={`wk-daybtn ${v?.action === "week" && v.day === d ? "on" : ""}`}
            disabled={!(v?.action === "week" && v.day === d) && dayFull(d)}
            onClick={() => place(`inlet:${c.id}`, d)}
          >
            {WD[weekday(d)]}
          </button>
        ))}
        <button className={`wk-daybtn wide ${v?.action === "keep" ? "on" : ""}`} onClick={() => update((x) => ((x.inlet[c.id] = { action: "keep" }), x))}>
          入れる（期日なし）
        </button>
        <button className={`wk-daybtn wide drop ${v?.action === "skip" ? "on" : ""}`} onClick={() => update((x) => ((x.inlet[c.id] = { action: "skip" }), x))}>
          見送る
        </button>
        {v && (
          <button className="wk-daybtn off" onClick={() => update((x) => (delete x.inlet[c.id], x))} aria-label="決めずに戻す">
            <Icon name="x" size={14} />
          </button>
        )}
      </div>
      {c.source_ref && (
        <a className="wk-link" href={c.source_ref} target="_blank" rel="noreferrer">
          元の発言を見る
        </a>
      )}
    </article>
  );
}

/* ---------------------------------------------------------------- ③ 確定 */

function Confirm({
  s,
  st,
  update,
  byId,
  saving,
  locked,
  onCommit,
}: {
  s: Snapshot;
  st: WeekState;
  update: (fn: (x: WeekState) => WeekState) => void;
  byId: Map<string, Candidate>;
  saving: boolean;
  locked: boolean;
  onCommit: () => void;
}) {
  const plan = useMemo(() => buildPlan(s, st), [s, st]);
  const kept = s.recommended.filter((r) => st.slots[r.id] === r.day).length;
  const moved = s.recommended.filter((r) => st.slots[r.id] && st.slots[r.id] !== r.day).length;
  const removed = s.recommended.filter((r) => !st.slots[r.id]).length;
  const added = plan.set_due.filter((x) => !s.recommended.some((r) => r.id === x.id)).length;
  const notPicked = s.dated_in_week.filter((x) => !st.slots[x.id]);
  const title = (id: string) => byId.get(id)?.title || id;

  return (
    <div className="wk-section">
      <div className="wk-stats">
        <div className="wk-stat good"><b>{kept}</b><span>AI案のまま</span></div>
        <div className="wk-stat"><b>{moved}</b><span>曜日を移した</span></div>
        <div className="wk-stat warn"><b>{removed}</b><span>AI案から外した</span></div>
        <div className="wk-stat"><b>{added}</b><span>自分で足した</span></div>
      </div>
      <p className="meta">この違いと理由が判断ログに残り、来週のおすすめの並べ方を直す材料になります。</p>
      {Object.values(st.left).some((a) => !a.tags.length && a.next === "keep") && (
        <div className="wk-banner">
          <Icon name="warn" size={18} />
          <span>振り返りがまだのものがあります。理由が残ると、来週の案が良くなります（このままでも確定できます）。</span>
        </div>
      )}

      <h2 className="wk-h">Todoist に入る期日</h2>
      {s.days.map((d) => {
        const items = [
          ...plan.set_due.filter((x) => x.date === d).map((x) => ({ k: x.id, t: title(x.id), why: st.reasons[x.id]?.text || "" })),
          ...plan.inlet.filter((x) => x.date === d).map((x) => ({ k: `i${x.topic_id}`, t: `入口から: ${x.title}`, why: "" })),
        ];
        return (
          <div key={d} className="glass wk-sum-day">
            <div className="wk-sum-head">
              <strong>{dayLabel(d)}</strong>
              <span className="meta">{items.length}/{s.per_day}</span>
            </div>
            {items.length === 0 && <p className="meta">（空き）</p>}
            {items.map((x) => (
              <div key={x.k} className="wk-sum-item">
                <span>{x.t}</span>
                {x.why && <small>{x.why}</small>}
              </div>
            ))}
          </div>
        );
      })}

      {notPicked.length > 0 && (
        <>
          <h2 className="wk-h">この週に期日があるが選ばなかったもの</h2>
          {notPicked.map((x) => (
            <label key={x.id} className="glass wk-keep">
              <input
                type="checkbox"
                checked={x.hard || !!st.keepDate[x.id]}
                disabled={x.hard}
                onChange={(e) => {
                  const on = e.target.checked;
                  update((y) => ((y.keepDate[x.id] = on), y));
                }}
              />
              <span>
                {x.title} <small className="meta">{dayLabel(x.date)}</small>
              </span>
              <span className={`wk-badge ${x.hard ? "hard" : ""}`}>{x.hard ? "約束・行事なので残す" : st.keepDate[x.id] ? "期日を残す" : "期日を外す"}</span>
            </label>
          ))}
        </>
      )}

      {(plan.notes.length > 0 || plan.inlet.length > 0 || plan.inlet_skip.length > 0) && (
        <>
          <h2 className="wk-h">ほかに反映すること</h2>
          <ul className="wk-done">
            {plan.notes.map((n) => (
              <li key={`n${n.id}`}><Icon name="list" size={14} /> {title(n.id)}：{n.text}</li>
            ))}
            {plan.inlet.filter((x) => !x.date).map((x) => (
              <li key={`k${x.topic_id}`}><Icon name="inbox" size={14} /> 入口から期日なしで入れる：{x.title}</li>
            ))}
            {plan.inlet_skip.map((id) => (
              <li key={`s${id}`}><Icon name="x" size={14} /> 入口で見送る：{s.inlet.find((c) => c.id === id)?.title || id}</li>
            ))}
          </ul>
        </>
      )}

      {s.hard_ahead.length > 0 && (
        <>
          <h2 className="wk-h">2〜3週先の動かせない日付</h2>
          <ul className="wk-done">
            {s.hard_ahead.map((h) => (
              <li key={h.id}><Icon name="warn" size={14} /> {dayLabel(h.date)} {h.title}</li>
            ))}
          </ul>
        </>
      )}

      <button className="cta" disabled={saving || locked} onClick={onCommit}>
        {locked ? "この週は確定済み" : saving ? "記録しています…" : `確定する（期日 ${plan.set_due.length + plan.inlet.filter((x) => x.date).length} 件・外す ${plan.clear_due.length} 件）`}
      </button>
      <p className="meta">確定すると判断ログに残り、30分以内に Todoist に反映されます。312 はタスクを閉じません（「やめる」はコメントだけ。片付けは 313）。</p>
    </div>
  );
}
