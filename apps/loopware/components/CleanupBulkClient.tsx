"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ACT_LABEL,
  addDaysIso,
  buildCleanupDecisions,
  type Choice,
  type Choices,
  type CleanupCard,
  type CleanupSnapshot,
} from "@/lib/cleanupBulk";

type Act = Choice["act"];
const ACTS: Act[] = ["close", "keep", "reschedule", "drop"];

function todayIso(): string {
  return new Date(Date.now() + 9 * 3600_000).toISOString().slice(0, 10);
}

/** おすすめを初期の選択にする（外せる）。keep は「残す」を選んだ扱いにはせず未選択のまま */
function fromSuggest(cards: CleanupCard[]): Choices {
  const out: Choices = {};
  for (const c of cards) if (c.suggest === "close" || c.suggest === "drop") out[c.id] = { act: c.suggest };
  return out;
}

export default function CleanupBulkClient() {
  const [snap, setSnap] = useState<CleanupSnapshot | null>(null);
  const [err, setErr] = useState("");
  const [ch, setCh] = useState<Choices>({});
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [bulkDue, setBulkDue] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    fetch("/api/cleanup", { cache: "no-store" })
      .then((r) => r.json())
      .then((j) => {
        if (!j.ok) throw new Error(j.error || "読み込めませんでした");
        setSnap(j.snapshot);
        if (j.snapshot) setCh(fromSuggest(j.snapshot.cards));
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  const cards = snap?.cards || [];
  const nPicked = useMemo(() => Object.values(picked).filter(Boolean).length, [picked]);
  const counts = useMemo(() => {
    const n: Record<string, number> = { close: 0, drop: 0, reschedule: 0, keep: 0 };
    for (const c of Object.values(ch)) n[c.act] += 1;
    return n;
  }, [ch]);
  const decided = Object.keys(ch).length;

  function setOne(id: string, v: Choice | null) {
    setCh((p) => {
      const n = { ...p };
      if (v) n[id] = v;
      else delete n[id];
      return n;
    });
  }

  function applyToPicked(act: Act, due?: string) {
    setCh((p) => {
      const n = { ...p };
      for (const [id, on] of Object.entries(picked)) if (on) n[id] = { act, due };
      return n;
    });
    setPicked({});
  }

  async function submit() {
    if (!snap) return;
    const rows = buildCleanupDecisions(cards, ch, Date.now().toString(36), new Date().toISOString());
    if (!rows.length) return setMsg("選んだものがありません");
    setSaving(true);
    setMsg("");
    try {
      const r = await fetch("/api/cleanup", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ decisions: rows }) });
      const j = await r.json();
      if (!j.ok && !j.saved) throw new Error(j.error || "保存できませんでした");
      const done = new Set(rows.map((x) => x.targetId));
      setSnap({ ...snap, cards: cards.filter((c) => !done.has(c.id)) });
      setCh({});
      setMsg(`${j.saved} 件を記録しました。30分以内に Todoist へ反映されます${j.failed?.length ? `（記録できなかった ${j.failed.length} 件）` : ""}`);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  if (err) return <p className="meta">{err}</p>;
  if (!snap) return <p className="meta">読み込み中…</p>;
  if (!cards.length)
    return (
      <div className="glass wk-empty">
        <b>いま片付ける候補はありません</b>
        <span className="meta">{msg || "材料は 30 分ごとに更新されます（スター付きメール由来のタスク）。"}</span>
      </div>
    );

  return (
    <div className="wk-section">
      <div className="glass wk-head">
        <div>
          <div className="meta">
            {snap.from_318 ? `318の判断依頼 ${snap.from_318} 件＋スター付きメール由来 ${snap.total - snap.from_318} 件` : `スター付きメール由来 ${snap.total} 件`}
          </div>
          <div className="wk-progress">
            <b>{decided}</b>
            <span>件を選んだ（完了 {counts.close}／削除 {counts.drop}／日を変更 {counts.reschedule}／残す {counts.keep}）</span>
          </div>
        </div>
        <button className="primary" disabled={saving || !decided} onClick={submit}>
          {saving ? "保存中…" : "確定する"}
        </button>
      </div>
      {msg && <div className="wk-banner ok"><span>{msg}</span></div>}

      <div className="glass wk-card">
        <div className="meta">チェックしたものを まとめて（{nPicked} 件）</div>
        <div className="btn-row">
          <button disabled={!nPicked} onClick={() => applyToPicked("close")}>完了</button>
          <button disabled={!nPicked} onClick={() => applyToPicked("keep")}>残す</button>
          <button disabled={!nPicked} onClick={() => applyToPicked("drop")}>削除</button>
          <button disabled={!nPicked} onClick={() => applyToPicked("reschedule", addDaysIso(todayIso(), 7))}>1週間後</button>
          <input type="date" value={bulkDue} onChange={(e) => setBulkDue(e.target.value)} aria-label="日付" />
          <button disabled={!nPicked || !bulkDue} onClick={() => applyToPicked("reschedule", bulkDue)}>この日に</button>
        </div>
        <button className="wk-link" onClick={() => setPicked(Object.fromEntries(cards.map((c) => [c.id, true])))}>全部チェック</button>
        <button className="wk-link" onClick={() => setPicked({})}>チェックを外す</button>
      </div>

      {cards.map((c) => {
        const v = ch[c.id];
        return (
          <div key={c.id} className="glass wk-card">
            <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
              <input type="checkbox" checked={!!picked[c.id]} onChange={(e) => setPicked((p) => ({ ...p, [c.id]: e.target.checked }))} />
              <span style={{ flex: 1 }}>
                <b>{c.title}</b>
                <span className="meta" style={{ display: "block" }}>
                  {[
                    c.origin === "318" && "318 判断依頼",
                    c.sender,
                    c.mail_date && `${c.mail_date}のメール`,
                    c.age_days != null && `${c.age_days}日前`,
                    (c.deadline || (c.origin === "318" && c.due)) && `期限 ${c.deadline || c.due}`,
                    c.prev,
                  ].filter(Boolean).join("｜")}
                </span>
              </span>
            </label>
            {c.summary && <div className="meta">{c.summary}</div>}
            <div className="meta">おすすめ: {c.suggest === "keep" ? "残す" : ACT_LABEL[c.suggest]}（{c.why}）</div>
            <div className="btn-row">
              {ACTS.map((a) => (
                <button
                  key={a}
                  className={v?.act === a ? "primary" : ""}
                  onClick={() => setOne(c.id, v?.act === a ? null : { act: a, due: a === "reschedule" ? addDaysIso(todayIso(), 7) : undefined })}
                >
                  {ACT_LABEL[a]}
                </button>
              ))}
              {c.gmail_url && (
                <a className="wk-link" href={c.gmail_url} target="_blank" rel="noreferrer">メールを開く</a>
              )}
            </div>
            {v?.act === "reschedule" && (
              <input type="date" value={v.due || ""} onChange={(e) => setOne(c.id, { act: "reschedule", due: e.target.value })} aria-label="新しい日" />
            )}
          </div>
        );
      })}
    </div>
  );
}
