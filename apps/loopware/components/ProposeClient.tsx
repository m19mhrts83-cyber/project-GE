"use client";

import { useEffect, useMemo, useState } from "react";
import Icon from "./Icon";
import VoiceDock, { CommentList } from "./VoiceDock";
import { useVoiceLog } from "./useVoiceLog";
import SaveSheet, { type SaveLine, type SaveStatus } from "./SaveSheet";
import {
  EDIT_TAGS,
  NONE,
  SEED_PROPOSALS,
  VERDICTS,
  WHY_TAGS,
  type Proposal,
  type Verdict,
} from "@/lib/proposals";
import {
  loadStore,
  removeDecision,
  upsertDecision,
  type DecisionRecord,
} from "@/lib/storage";

type Step = "sort" | "why" | "done";

const tid = (p: Proposal) => `prop-${p.id}`;
const vLabel = (v: Verdict) => VERDICTS.find((x) => x.id === v)?.label ?? v;

export default function ProposeClient() {
  const [items, setItems] = useState<Proposal[]>(SEED_PROPOSALS);
  const [verdict, setVerdict] = useState<Record<string, Verdict>>({});
  const [comment, setComment] = useState<Record<string, string>>({});
  const [why, setWhy] = useState<Record<string, string[]>>({});
  const [edits, setEdits] = useState<Record<string, { title: string; doneWhen: string; due: string }>>({});
  const [editOpen, setEditOpen] = useState<Record<string, boolean>>({});
  const [editWhy, setEditWhy] = useState<Record<string, string[]>>({});
  const [scope, setScope] = useState<Record<string, "once" | "rule">>({});
  const [step, setStep] = useState<Step>("sort");
  const [isSample, setIsSample] = useState(true);
  const voice = useVoiceLog("312");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [saved, setSaved] = useState<{
    rec: DecisionRecord;
    lines: SaveLine[];
    total: number;
    added: number;
    status: SaveStatus;
  } | null>(null);

  // 実データ（miss_scan の候補）があれば差し替える
  useEffect(() => {
    fetch("/api/misses")
      .then((r) => r.json())
      .then((j) => {
        if (Array.isArray(j?.candidates) && j.candidates.length) {
          setIsSample(false);
          setItems(
            j.candidates.map((c: { id: string; source: string; folder: string; snippet: string; hypothesis: string }) => ({
              id: c.id,
              group: c.id,
              source: c.source,
              from: c.folder,
              sourceText: c.snippet,
              taskTitle: c.snippet.slice(0, 40),
              hypothesis: c.hypothesis,
            })),
          );
        }
      })
      .catch(() => undefined);
  }, []);

  // 音声の対象：タップしたカード。最初は先頭の未仕分けカード
  useEffect(() => {
    if (items.length && (!activeId || !items.some((it) => it.id === activeId))) {
      setActiveId((items.find((it) => !verdict[it.id]) ?? items[0]).id);
    }
  }, [items, activeId, verdict]);

  // 保存済みなら「仕分け済み」を復元
  useEffect(() => {
    const recs = loadStore().decisions.filter((d) => d.topicId.startsWith("prop-"));
    const v: Record<string, Verdict> = {};
    const w: Record<string, string[]> = {};
    const c: Record<string, string> = {};
    const sc: Record<string, "once" | "rule"> = {};
    for (const it of items) {
      const r = recs.find((d) => d.topicId === tid(it));
      if (r && (r.choice === "take" || r.choice === "skip" || r.choice === "hold")) {
        v[it.id] = r.choice;
        w[it.id] = r.reasonTags;
        if (r.freeNote) c[it.id] = r.freeNote;
        if (r.scope) sc[it.id] = r.scope;
      }
    }
    if (items.length && items.every((it) => v[it.id])) {
      setVerdict(v);
      setWhy(w);
      setComment(c);
      setScope(sc);
      setStep("done");
    }
  }, [items]);

  const sortedN = items.filter((it) => verdict[it.id]).length;
  const counts = useMemo(() => {
    const n = { take: 0, skip: 0, hold: 0 } as Record<Verdict, number>;
    for (const it of items) if (verdict[it.id]) n[verdict[it.id]]++;
    return n;
  }, [items, verdict]);
  const notChosen = items.filter(
    (it) => verdict[it.id] === "skip" || verdict[it.id] === "hold",
  );

  function setV(id: string, v: Verdict | null) {
    const next = { ...verdict };
    if (v) next[id] = v;
    else delete next[id];
    setVerdict(next);
  }

  function toggleWhy(id: string, tag: string) {
    const cur = why[id] ?? [];
    setWhy({
      ...why,
      [id]: cur.includes(tag) ? cur.filter((t) => t !== tag) : [...cur, tag],
    });
  }

  async function save() {
    const at = new Date().toISOString();
    const finalOf = (it: Proposal) => {
      const e = edits[it.id];
      const title = e?.title || it.taskTitle;
      const done = e?.doneWhen ?? it.doneWhen;
      const due = e?.due ?? it.due;
      return [`タスク：${title}`, done ? `完了条件：${done}` : "", due ? `期限：${due}` : "", it.project ? `プロジェクト：${it.project}` : ""]
        .filter(Boolean)
        .join("\n");
    };
    const beforeOf = (it: Proposal) =>
      [`タスク：${it.taskTitle}`, it.doneWhen ? `完了条件：${it.doneWhen}` : "", it.due ? `期限：${it.due}` : "", it.project ? `プロジェクト：${it.project}` : ""]
        .filter(Boolean)
        .join("\n");
    const recs: DecisionRecord[] = items.map((it) => {
      const isTake = verdict[it.id] === "take";
      const edited = isTake && !!edits[it.id] && finalOf(it) !== beforeOf(it);
      return {
        topicId: tid(it),
        agentId: "312",
        choice: verdict[it.id],
        finalText: isTake ? finalOf(it) : it.taskTitle,
        beforeText: edited ? beforeOf(it) : undefined,
        afterText: edited ? finalOf(it) : undefined,
        reasonTags: isTake ? (edited ? (editWhy[it.id] ?? []) : []) : (why[it.id] ?? []),
        freeNote: comment[it.id] || undefined,
        decidedAt: at,
        decidedVia: "app",
        scope: scope[it.id] ?? "once",
      };
    });
    recs.forEach(upsertDecision);

    const whyCount = notChosen.filter((it) => (why[it.id] ?? []).length > 0).length;
    const comments = items.filter((it) => comment[it.id]).length;
    const tally: Record<string, number> = {};
    notChosen.forEach((it) => (why[it.id] ?? []).forEach((t) => (tally[t] = (tally[t] ?? 0) + 1)));
    const lines: SaveLine[] = [
      { k: "take", v: `採る ${counts.take}件` },
      { k: "skip", v: `見送る ${counts.skip}件` },
      { k: "hold", v: `保留 ${counts.hold}件` },
      {
        k: "reason",
        v: notChosen.length
          ? Object.entries(tally).map(([t, n]) => `${t}×${n}`).join("・") ||
            `選ばなかった${notChosen.length}件は理由なし（任意）`
          : "選ばなかった提案なし",
      },
      { k: "comment", v: comments ? `Todoist 用コメント ${comments}件` : "コメントなし" },
      {
        k: "edit",
        v: (() => {
          const n = recs.filter((r) => r.beforeText).length;
          return n ? `直して採る ${n}件（直す前と後を保存）` : "文面の修正なし";
        })(),
      },
      {
        k: "scope",
        v: (() => {
          const n = recs.filter((r) => r.scope === "rule").length;
          return n ? `次も同じに ${n}件（承認するまで基準にしない）` : "すべて今回だけ";
        })(),
      },
      {
        k: "voice",
        v: (() => {
          const n = items.reduce((a, it) => a + voice.forTarget(tid(it)).length, 0);
          return n ? `音声・文字コメント ${n}件（カードごとにログへ）` : "音声コメントなし";
        })(),
      },
    ];
    const batch: DecisionRecord = {
      topicId: `prop-batch-${at}`,
      agentId: "312",
      choice: "take",
      finalText: recs
        .map((r, i) => `- [${vLabel(r.choice as Verdict)}] ${items[i].taskTitle}${r.reasonTags.length ? `（${r.reasonTags.join("・")}）` : ""}${r.freeNote ? ` // ${r.freeNote}` : ""}`)
        .join("\n"),
      reasonTags: Object.keys(tally),
      decidedAt: at,
      decidedVia: "app",
    };
    setSaved({
      rec: batch,
      lines,
      total: loadStore().decisions.length,
      added: recs.length,
      status: "pending",
    });
    void whyCount;

    try {
      const results = await Promise.all(
        recs.map((r, i) =>
          fetch("/api/decide", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              agentId: "312",
              topicText: `[提案:${items[i].source}] ${items[i].sourceText || items[i].related || ""}\n→ ${items[i].taskTitle}`,
              seedId: r.topicId,
              decision: r,
            }),
          }).then((x) => x.json().catch(() => null)),
        ),
      );
      const ok = results.every((j) => j && j.persisted !== false);
      setSaved((c) => (c ? { ...c, status: ok ? "server" : "local" } : c));
    } catch {
      setSaved((c) => (c ? { ...c, status: "local" } : c));
    }
  }

  function reopenAll() {
    items.forEach((it) => removeDecision(tid(it), "312"));
    setVerdict({});
    setWhy({});
    setComment({});
    setEdits({});
    setEditOpen({});
    setEditWhy({});
    setScope({});
    setSaved(null);
    setStep("sort");
  }

  /* ---------- 仕分け済み ---------- */
  if (step === "done") {
    return (
      <div>
        <div className="card done-card">
          <div className="done-head">
            <span className="radio" style={{ background: "var(--positive)", borderColor: "var(--positive)" }}>
              <Icon name="check" size={12} stroke={3.5} />
            </span>
            <span style={{ flexGrow: 1 }}>仕分け済み</span>
            <span className="done-badge">保存済み</span>
          </div>
          <div className="tally">
            {VERDICTS.map((v) => (
              <div key={v.id} className={`tally-i ${v.id}`}>
                <b className="mono">{items.filter((it) => verdict[it.id] === v.id).length}</b>
                <span>{v.label}</span>
              </div>
            ))}
          </div>
          <ul className="list" style={{ padding: 0 }}>
            {items.map((it) => (
              <li key={it.id}>
                <div className="row">
                  <span className={`vchip ${verdict[it.id]}`}>{vLabel(verdict[it.id])}</span>
                  <span style={{ flexGrow: 1 }}>{it.taskTitle}</span>
                </div>
                {(why[it.id] ?? []).length || comment[it.id] ? (
                  <div className="meta">
                    {[...(why[it.id] ?? []), comment[it.id]].filter(Boolean).join(" ／ ")}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
          <button type="button" className="secondary" onClick={reopenAll}>
            <Icon name="back" size={16} /> やっぱり見直す
          </button>
        </div>
      </div>
    );
  }

  /* ---------- 選ばなかった理由 ---------- */
  if (step === "why") {
    return (
      <div>
        {saved ? (
          <SaveSheet
            rec={saved.rec}
            decisionLabel={`${items.length}件を仕分けて保存`}
            lines={saved.lines}
            total={saved.total}
            added={saved.added}
            status={saved.status}
            onClose={() => {
              setSaved(null);
              setStep("done");
            }}
          />
        ) : null}
        <div className="eyebrow">
          選ばなかった理由<small>押すだけ・空でも保存できる</small>
        </div>
        <p className="meta" style={{ margin: "0 0 10px" }}>
          見送り・保留 {notChosen.length}件。「知っている」「今は不要」「誤り」は別々に残します。
        </p>
        {notChosen.map((it) => {
          const v = verdict[it.id] as "skip" | "hold";
          return (
            <div key={it.id} className="card" style={{ marginBottom: 12 }}>
              <div className="row" style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
                <span className={`vchip ${v}`}>{vLabel(v)}</span>
                <strong style={{ fontSize: 14 }}>{it.taskTitle}</strong>
              </div>
              <div className="tags">
                {WHY_TAGS[v].map((t) => {
                  const on = (why[it.id] ?? []).includes(t);
                  return (
                    <button
                      key={t}
                      type="button"
                      className={`tag ${on ? "on" : ""}`}
                      aria-pressed={on}
                      onClick={() => toggleWhy(it.id, t)}
                    >
                      {t}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
        <div className="bar">
          <div className="bar-in">
            <button type="button" className="secondary" onClick={() => setStep("sort")}>
              <Icon name="back" size={16} /> 仕分けに戻る
            </button>
            <button type="button" className="cta big" onClick={save}>
              <Icon name="check" size={20} stroke={2.6} />
              保存する
            </button>
          </div>
        </div>
      </div>
    );
  }

  /* ---------- 仕分け ---------- */
  return (
    <div>
      {saved ? (
        <SaveSheet
          rec={saved.rec}
          decisionLabel={`${items.length}件を仕分けて保存`}
          lines={saved.lines}
          total={saved.total}
          added={saved.added}
          status={saved.status}
          onClose={() => {
            setSaved(null);
            setStep("done");
          }}
        />
      ) : null}
      <div className="progress" aria-label={`仕分け ${sortedN} / ${items.length}`}>
        <div className="progress-bar">
          <i style={{ width: `${(sortedN / Math.max(1, items.length)) * 100}%` }} />
        </div>
        <span className="mono">
          <b>{sortedN}</b> / {items.length}
        </span>
      </div>
      <p className="meta" style={{ margin: "0 0 12px" }}>
        {isSample ? "サンプルの提案です。" : "各ソースから拾った候補です。"}
        採ったものだけ Todoist に出す前提で、コメントも一緒に残します。
      </p>

      {items.map((it) => {
        const v = verdict[it.id];
        return (
          <div
            key={it.id}
            data-tid={tid(it)}
            data-tlabel={it.taskTitle}
            className={`card pcard targetable ${v ?? ""} ${activeId === it.id ? "is-target" : ""}`}
            onClick={() => setActiveId(it.id)}
          >
            <div className="p-src">
              <span className="src-badge">{it.source}</span>
              <span className="meta">{it.from}</span>
            </div>
            {it.sourceText ? <p className="p-snip">原文：{it.sourceText}</p> : null}
            <div className="p-task">
              <div className="eyebrow" style={{ margin: 0 }}>提案タスク</div>
              <div className="p-title">{edits[it.id]?.title || it.taskTitle}</div>
              <dl className="p-fields">
                <div><dt>完了条件</dt><dd>{edits[it.id]?.doneWhen ?? it.doneWhen ?? "未設定"}</dd></div>
                <div><dt>{it.requested ? "依頼された箇所" : "関連する原文"}</dt><dd>{it.requested || it.related || NONE}</dd></div>
                <div><dt>担当者</dt><dd className={it.assignee ? "" : "none"}>{it.assignee || NONE}</dd></div>
                <div><dt>期限</dt><dd className={(edits[it.id]?.due ?? it.due) ? "" : "none"}>{edits[it.id]?.due ?? it.due ?? NONE}</dd></div>
                {it.status ? <div><dt>原文の作業状況</dt><dd>{it.status}</dd></div> : null}
              </dl>
            </div>
            {it.hypothesis ? (
              <div className="ai-guess">
                <span className="ai-tag">AIの推測</span>
                {it.hypothesis}
              </div>
            ) : null}

            {!v ? (
              <div className="v3">
                {VERDICTS.map((x) => (
                  <button
                    key={x.id}
                    type="button"
                    className={`vbtn ${x.id}`}
                    onClick={() => setV(it.id, x.id)}
                  >
                    <Icon name={x.icon} size={20} stroke={2.4} />
                    <strong>{x.label}</strong>
                    <small>{x.desc}</small>
                  </button>
                ))}
              </div>
            ) : (
              <>
                <div className="v-chosen">
                  <span className={`vbtn on ${v}`} role="status">
                    <Icon name={VERDICTS.find((x) => x.id === v)!.icon} size={18} stroke={3} />
                    {vLabel(v)}
                  </span>
                  <button type="button" className="redo" onClick={() => setV(it.id, null)}>
                    <Icon name="back" size={16} /> 見直す
                  </button>
                </div>
                {v === "take" ? (
                  <>
                    <button
                      type="button"
                      className="linkbtn"
                      onClick={() => {
                        setEditOpen({ ...editOpen, [it.id]: !editOpen[it.id] });
                        if (!edits[it.id])
                          setEdits({
                            ...edits,
                            [it.id]: { title: it.taskTitle, doneWhen: it.doneWhen ?? "", due: it.due ?? "" },
                          });
                      }}
                    >
                      {editOpen[it.id] ? "文面の修正を閉じる" : "採る文面を直す"}
                    </button>
                    {editOpen[it.id] && edits[it.id] ? (
                      <div className="editbox">
                        <label>タスク名
                          <input type="text" value={edits[it.id].title} onChange={(e) => setEdits({ ...edits, [it.id]: { ...edits[it.id], title: e.target.value } })} />
                        </label>
                        <label>完了条件（ここまでできたら完了）
                          <input type="text" value={edits[it.id].doneWhen} onChange={(e) => setEdits({ ...edits, [it.id]: { ...edits[it.id], doneWhen: e.target.value } })} />
                        </label>
                        <label>期限（原文に無ければ空のまま）
                          <input type="text" value={edits[it.id].due} onChange={(e) => setEdits({ ...edits, [it.id]: { ...edits[it.id], due: e.target.value } })} />
                        </label>
                        <div className="meta">直した理由（任意）</div>
                        <div className="tags">
                          {EDIT_TAGS.map((t) => {
                            const on = (editWhy[it.id] ?? []).includes(t);
                            return (
                              <button key={t} type="button" className={`tag ${on ? "on" : ""}`} aria-pressed={on}
                                onClick={() => setEditWhy({ ...editWhy, [it.id]: on ? (editWhy[it.id] ?? []).filter((x) => x !== t) : [...(editWhy[it.id] ?? []), t] })}>
                                {t}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ) : null}
                  </>
                ) : null}
                <input
                  type="text"
                  value={comment[it.id] ?? ""}
                  onChange={(e) => setComment({ ...comment, [it.id]: e.target.value })}
                  placeholder={v === "take" ? "Todoist に残すコメント（任意）" : "一言（任意）"}
                  aria-label="コメント"
                />
              </>
            )}
            {v ? (
              <div className="scope" role="group" aria-label="この判断の使い方">
                <button type="button" className={(scope[it.id] ?? "once") === "once" ? "on" : ""} onClick={() => setScope({ ...scope, [it.id]: "once" })}>今回だけ</button>
                <button type="button" className={scope[it.id] === "rule" ? "on" : ""} onClick={() => setScope({ ...scope, [it.id]: "rule" })}>次も同じに</button>
              </div>
            ) : null}
            <CommentList comments={voice.forTarget(tid(it))} onDelete={voice.remove} onMove={voice.reassign} />
          </div>
        );
      })}

      <div className="bar">
        <div className="bar-in">
          <VoiceDock
            onComment={voice.add}
          />
          <button
            type="button"
            className="cta big"
            disabled={sortedN < items.length}
            onClick={() => (notChosen.length ? setStep("why") : save())}
          >
            {sortedN < items.length
              ? `あと${items.length - sortedN}件を仕分ける`
              : notChosen.length
                ? "選ばなかった理由へ"
                : "保存する"}
          </button>
        </div>
      </div>
    </div>
  );
}
