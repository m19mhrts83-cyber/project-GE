"use client";

import { useEffect, useState } from "react";
import AllClear from "./AllClear";
import {
  CLOSE_LEAK_LABEL,
  buildCloseLeakDecisions,
  type CloseLeakAct,
  type CloseLeakCard,
} from "@/lib/closeLeak";

const CONF_LABEL: Record<CloseLeakCard["confidence"], string> = { high: "根拠 強", medium: "根拠 中", low: "根拠 弱" };

function fmt(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ja-JP", { timeZone: "Asia/Tokyo", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

/** 313 閉じ漏れ。外で済んだ痕跡があるのに Todoist に残っている件を 済み／残す で選ぶ（おすすめの初期選択はしない） */
export default function CloseLeakClient() {
  const [cards, setCards] = useState<CloseLeakCard[] | null>(null);
  const [connected, setConnected] = useState(true);
  const [at, setAt] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const [ch, setCh] = useState<Record<string, CloseLeakAct>>({});
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    fetch("/api/closeleak", { cache: "no-store" })
      .then((r) => r.json())
      .then((j) => {
        if (!j.ok) throw new Error(j.error || "読み込めませんでした");
        setConnected(!!j.connected);
        setAt(j.generated_at);
        setCards(j.cards || []);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  const decided = Object.keys(ch).length;
  const nClose = Object.values(ch).filter((a) => a === "close").length;

  async function submit() {
    if (!cards) return;
    const rows = buildCloseLeakDecisions(cards, ch, Date.now().toString(36), new Date().toISOString());
    if (!rows.length) return setMsg("選んだものがありません");
    setSaving(true);
    setMsg("");
    try {
      const r = await fetch("/api/cleanup", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ decisions: rows }) });
      const j = await r.json();
      if (!j.ok && !j.saved) throw new Error(j.error || "保存できませんでした");
      const done = new Set(rows.map((x) => x.targetId));
      setCards(cards.filter((c) => !done.has(c.id)));
      setCh({});
      setMsg(`${j.saved} 件を記録しました。済みは30分以内に Todoist で完了になります${j.failed?.length ? `（記録できなかった ${j.failed.length} 件）` : ""}`);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  if (err) return <p className="meta">{err}</p>;
  if (!cards) return <p className="meta">読み込み中…</p>;
  if (!connected)
    return (
      <div className="glass wk-empty">
        <b>閉じ漏れの検知結果は、まだ一度も届いていません</b>
        <span className="meta">Mac の検知（毎日 19:30）が初めて走ると、ここに並びます。</span>
      </div>
    );
  if (!cards.length)
    return (
      <div>
        {msg && <div className="wk-banner ok"><span>{msg}</span></div>}
        <AllClear title="閉じ漏れはありません" sub="外で済んで残っているタスクは見つかりませんでした" />
        <p className="meta">最終検知 {fmt(at)}（Mac・毎日 19:30）</p>
      </div>
    );

  return (
    <div className="wk-section bulk">
      <div className="glass wk-head">
        <div>
          <div className="meta">外で済んだ痕跡（パートナーへの送信記録）があるのに Todoist に残っている件。最終検知 {fmt(at)}</div>
          <div className="wk-progress">
            <b>{decided}</b>
            <span>件を選んだ（済み {nClose}／残す {decided - nClose}）</span>
          </div>
        </div>
        <button className="primary bulk-submit" disabled={saving || !decided} onClick={submit}>
          {saving ? "保存中…" : "確定する"}
        </button>
      </div>
      {msg && <div className="wk-banner ok"><span>{msg}</span></div>}

      {cards.map((c) => {
        const v = ch[c.id];
        return (
          <div key={c.id} className="glass wk-card">
            <b>{c.title}</b>
            <span className="meta" style={{ display: "block" }}>
              {[CONF_LABEL[c.confidence] || c.confidence, c.streak_days && c.streak_days > 1 ? `${c.streak_days}日続けて検知` : ""].filter(Boolean).join("｜")}
            </span>
            <div className="meta">{c.why}</div>
            {c.evidence.map((e, i) => (
              <div key={i} className="meta">・{e.folder}{e.subject ? ` ／ ${e.subject}` : ""}{e.at ? `（${fmt(e.at)}）` : ""}</div>
            ))}
            <div className="btn-row">
              {(["close", "keep"] as CloseLeakAct[]).map((a) => (
                <button
                  key={a}
                  className={v === a ? "primary" : ""}
                  onClick={() =>
                    setCh((p) => {
                      const n = { ...p };
                      if (n[c.id] === a) delete n[c.id];
                      else n[c.id] = a;
                      return n;
                    })
                  }
                >
                  {CLOSE_LEAK_LABEL[a]}
                </button>
              ))}
              <a className="wk-link" href={`https://app.todoist.com/app/task/${c.id}`} target="_blank" rel="noreferrer">
                Todoist で開く
              </a>
            </div>
          </div>
        );
      })}
    </div>
  );
}
