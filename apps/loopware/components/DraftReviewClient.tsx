"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Icon from "@/components/Icon";
import { useSpeech } from "@/components/useSpeech";
import {
  currentVersion,
  diffStats,
  diffText,
  type DraftComment,
  type DraftVersion,
} from "@/lib/draftCore";

type Draft = {
  id: string;
  case_name: string;
  recipient: string;
  channel: string;
  status: "open" | "done" | "dropped";
  context: string | null;
  versions: DraftVersion[];
  updated_at: string;
};

type Sel = { quote: string; start: number; end: number } | null;
type View = "diff" | "text" | "edit";

/** 箇所を選んで → 声（または文字）でダメ出し → AI が直す → 差分で確かめる */
export default function DraftReviewClient({ id }: { id: string }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const [toast, setToast] = useState("");
  const [view, setView] = useState<View>("text");
  const [sel, setSel] = useState<Sel>(null);
  const [pending, setPending] = useState("");
  const [comments, setComments] = useState<DraftComment[]>([]);
  const [editText, setEditText] = useState("");
  const [compareTo, setCompareTo] = useState<string>(""); // 比べる前の版
  const textRef = useRef<HTMLDivElement>(null);
  const viaRef = useRef<"voice" | "typed">("typed");

  const speech = useSpeech(
    useCallback((t: string) => {
      viaRef.current = "voice";
      setPending((p) => (p ? `${p} ${t}` : t));
    }, []),
  );

  const load = useCallback(async () => {
    setErr("");
    const r = await fetch(`/api/drafts/${id}`, { cache: "no-store" });
    const j = await r.json().catch(() => ({}));
    if (!j.ok) {
      setErr(j.error || `読み込めません（${r.status}）`);
      return;
    }
    setDraft(j.draft);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const live = useMemo(() => (draft ? draft.versions.filter((v) => !v.reverted) : []), [draft]);
  const cur = useMemo(() => (draft ? currentVersion(draft.versions) : null), [draft]);
  const prev = useMemo(() => {
    if (!cur || live.length < 2) return null;
    if (compareTo) return live.find((v) => v.label === compareTo && v !== cur) || null;
    return live[live.length - 2];
  }, [cur, live, compareTo]);
  const segs = useMemo(() => (cur && prev ? diffText(prev.text, cur.text) : []), [cur, prev]);
  const stats = useMemo(() => diffStats(segs), [segs]);

  // 新しい版ができたら差分を見せる
  const lastLabel = cur?.label;
  useEffect(() => {
    if (live.length >= 2) setView("diff");
    setCompareTo("");
  }, [lastLabel]); // eslint-disable-line react-hooks/exhaustive-deps

  function captureSelection() {
    const box = textRef.current;
    const s = window.getSelection();
    if (!box || !s || s.rangeCount === 0 || s.isCollapsed) return;
    const r = s.getRangeAt(0);
    if (!box.contains(r.startContainer) || !box.contains(r.endContainer)) return;
    const pre = document.createRange();
    pre.selectNodeContents(box);
    pre.setEnd(r.startContainer, r.startOffset);
    const start = pre.toString().length;
    const quote = r.toString();
    if (!quote.trim()) return;
    setSel({ quote, start, end: start + quote.length });
  }

  useEffect(() => {
    const h = () => {
      // スマホは長押し選択の後に selectionchange だけが来る
      if (view === "text") captureSelection();
    };
    document.addEventListener("selectionchange", h);
    return () => document.removeEventListener("selectionchange", h);
  }, [view]);

  function addComment() {
    const text = pending.trim();
    if (!text) return;
    if (speech.listening) speech.stop();
    setComments((cs) => [
      ...cs,
      { quote: sel?.quote || "", start: sel?.start ?? null, end: sel?.end ?? null, text, via: viaRef.current },
    ]);
    setPending("");
    viaRef.current = "typed";
    setSel(null);
    window.getSelection()?.removeAllRanges();
  }

  async function post(body: Record<string, unknown>, label: string) {
    if (!draft) return null;
    setBusy(label);
    setErr("");
    try {
      const r = await fetch(`/api/drafts/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...body, updatedAt: draft.updated_at }),
      });
      const j = await r.json().catch(() => ({}));
      if (j.draft) setDraft(j.draft);
      if (!j.ok) {
        setErr(j.error || `失敗しました（${r.status}）`);
        return null;
      }
      return j;
    } catch {
      setErr("通信できませんでした。もう一度どうぞ");
      return null;
    } finally {
      setBusy("");
    }
  }

  async function revise() {
    if (speech.listening) speech.stop();
    const list = pending.trim()
      ? [...comments, { quote: sel?.quote || "", start: sel?.start ?? null, end: sel?.end ?? null, text: pending.trim(), via: viaRef.current }]
      : comments;
    if (!list.length) {
      setErr("箇所を選んで、ダメ出しを1つ以上入れてください");
      return;
    }
    const j = await post({ op: "revise", comments: list }, "AI が直しています…");
    if (j) {
      setComments([]);
      setPending("");
      setSel(null);
      setToast(j.ruleHint ? `直しました。ルール候補: ${j.ruleHint}` : "直しました。差分を確かめてください");
    }
  }

  async function saveManual() {
    const j = await post({ op: "manual", text: editText, comments }, "保存しています…");
    if (j) {
      setComments([]);
      setToast("手直しを保存しました");
    }
  }

  async function revert() {
    if (!confirm("いまの版を戻して、1つ前の版に戻しますか？（記録は残ります）")) return;
    const j = await post({ op: "revert" }, "戻しています…");
    if (j) setToast("1つ前の版に戻しました");
  }

  async function done() {
    const j = await post({ op: "done" }, "確定しています…");
    if (j && cur) {
      try {
        await navigator.clipboard.writeText(cur.text);
        setToast("確定しました。文面をコピーしました");
      } catch {
        setToast("確定しました");
      }
    }
  }

  async function copy() {
    if (!cur) return;
    try {
      await navigator.clipboard.writeText(cur.text);
      setToast("コピーしました");
    } catch {
      setToast("コピーできませんでした");
    }
  }

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  if (err && !draft) return <div className="card warn">{err}</div>;
  if (!draft || !cur) return <div className="card meta">読み込み中…</div>;

  const open = draft.status === "open";
  const marks = [...comments]
    .filter((c) => c.start !== null && c.end !== null)
    .sort((a, b) => (a.start as number) - (b.start as number));

  return (
    <div className="list dr">
      <div className="card dr-head">
        <div className="eyebrow">
          {draft.recipient} ／ {draft.channel} ／ {open ? "直し中" : "確定済み"}
        </div>
        <strong>{draft.case_name}</strong>
        <div className="dr-versions">
          {draft.versions.map((v) => (
            <span key={v.label} className={`pill ${v === cur ? "on" : ""} ${v.reverted ? "off" : ""}`} title={v.reverted ? "戻した版" : ""}>
              {v.label}
              {v.by === "ai" ? "・AI" : v.by === "owner" ? "・手" : ""}
            </span>
          ))}
        </div>
      </div>

      <div className="tabs dr-tabs" role="tablist">
        <button className={`tab ${view === "text" ? "active" : ""}`} onClick={() => setView("text")} role="tab">
          文面（選んでダメ出し）
        </button>
        <button className={`tab ${view === "diff" ? "active" : ""}`} onClick={() => setView("diff")} role="tab" disabled={!prev}>
          差分{prev ? `（${stats.places}か所）` : ""}
        </button>
        {open ? (
          <button
            className={`tab ${view === "edit" ? "active" : ""}`}
            onClick={() => {
              setEditText(cur.text);
              setView("edit");
            }}
            role="tab"
          >
            手で直す
          </button>
        ) : null}
      </div>

      {view === "text" ? (
        <div className="card">
          <div className="meta">{open ? "直したい所を指でなぞって選び、下のマイクで話してください。" : "確定済みの文面です。"}</div>
          <div ref={textRef} className="dr-text" onMouseUp={captureSelection} onTouchEnd={captureSelection}>
            {renderMarked(cur.text, marks)}
          </div>
        </div>
      ) : null}

      {view === "diff" && prev ? (
        <div className="card">
          <div className="dr-compare meta">
            <label>
              比べる前の版
              <select value={prev.label} onChange={(e) => setCompareTo(e.target.value)}>
                {live
                  .filter((v) => v !== cur)
                  .map((v) => (
                    <option key={v.label} value={v.label}>
                      {v.label}
                    </option>
                  ))}
              </select>
            </label>
            <span>
              → {cur.label}　<span className="dr-ins">＋{stats.added}字</span> <span className="dr-del">−{stats.removed}字</span>
            </span>
          </div>
          <div className="dr-text">
            {segs.map((s, i) =>
              s.op === "eq" ? (
                <span key={i}>{s.text}</span>
              ) : s.op === "ins" ? (
                <ins key={i} className="dr-ins">
                  {s.text}
                </ins>
              ) : (
                <del key={i} className="dr-del">
                  {s.text}
                </del>
              ),
            )}
          </div>
          {cur.changes?.length ? (
            <div className="dr-changes">
              <div className="eyebrow">AI が直したところ</div>
              {cur.changes.map((c, i) => (
                <div key={i} className="dr-change">
                  <div className="meta">{c.why}</div>
                  <div>
                    <del className="dr-del">{c.before}</del> → <ins className="dr-ins">{c.after}</ins>
                  </div>
                </div>
              ))}
            </div>
          ) : null}
          {cur.comments?.length ? (
            <div className="dr-changes">
              <div className="eyebrow">このときのダメ出し</div>
              {cur.comments.map((c, i) => (
                <div key={i} className="meta">
                  {c.quote ? `「${c.quote.slice(0, 40)}」` : "全体"}：{c.text}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {view === "edit" && open ? (
        <div className="card editbox">
          <label>
            文面を直接直す（保存すると新しい版になり、差分が残ります）
            <textarea className="dr-edit" value={editText} onChange={(e) => setEditText(e.target.value)} rows={16} />
          </label>
          <div className="btn-row">
            <button className="primary" onClick={saveManual} disabled={!!busy || editText === cur.text}>
              手直しを保存
            </button>
            <button onClick={() => setView("text")}>やめる</button>
          </div>
        </div>
      ) : null}

      {open && view !== "edit" ? (
        <div className="card dr-dock">
          <div className="meta">{sel ? <>選んだ箇所：「{sel.quote.slice(0, 60)}{sel.quote.length > 60 ? "…" : ""}」</> : "箇所を選ばなければ、全体へのダメ出しになります"}</div>
          <div className="dr-input">
            {speech.supported ? (
              <button
                className={`vmic ${speech.listening ? "live" : ""}`}
                onClick={() => (speech.listening ? speech.stop() : speech.start())}
                aria-label={speech.listening ? "録音を止める" : "声でダメ出し"}
              >
                <Icon name={speech.listening ? "stop" : "mic"} size={22} />
              </button>
            ) : null}
            <textarea
              value={pending + (speech.interim ? ` ${speech.interim}` : "")}
              onChange={(e) => {
                viaRef.current = "typed";
                setPending(e.target.value);
              }}
              placeholder={speech.supported ? "マイクで話すか、ここに書く" : "ここにダメ出しを書く（このブラウザは音声入力に未対応）"}
              rows={2}
            />
          </div>
          {speech.error ? <div className="warn">{speech.error}</div> : null}
          <div className="btn-row">
            <button onClick={addComment} disabled={!pending.trim()}>
              ダメ出しに追加
            </button>
            <button className="primary" onClick={revise} disabled={!!busy || (!comments.length && !pending.trim())}>
              この指摘で直す{comments.length ? `（${comments.length + (pending.trim() ? 1 : 0)}件）` : ""}
            </button>
          </div>
          {comments.length ? (
            <div className="dr-comments">
              {comments.map((c, i) => (
                <div key={i} className="dr-comment">
                  <span className="meta">
                    {c.via === "voice" ? "🎤" : "✎"} {c.quote ? `「${c.quote.slice(0, 30)}${c.quote.length > 30 ? "…" : ""}」` : "全体"}
                  </span>
                  <span className="grow">{c.text}</span>
                  <button className="linkbtn" onClick={() => setComments((cs) => cs.filter((_, k) => k !== i))}>
                    消す
                  </button>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {busy ? <div className="card meta">{busy}</div> : null}
      {err ? <div className="card warn">{err}</div> : null}

      <div className="btn-row">
        <button onClick={copy}>いまの文面をコピー</button>
        {open && live.length >= 2 ? <button onClick={revert}>1つ前に戻す</button> : null}
        {open ? (
          <button className="primary" onClick={done} disabled={!!busy}>
            これで確定（コピー）
          </button>
        ) : (
          <button onClick={() => post({ op: "reopen" }, "開き直しています…")}>もう一度直す</button>
        )}
      </div>

      {toast ? <div className="desk-toast">{toast}</div> : null}
    </div>
  );
}

/** ダメ出し済みの箇所に印をつける（重なりは先のものを優先） */
function renderMarked(text: string, marks: DraftComment[]) {
  const out: React.ReactNode[] = [];
  let pos = 0;
  marks.forEach((m, i) => {
    const s = Math.max(m.start as number, pos);
    const e = Math.min(m.end as number, text.length);
    if (e <= s) return;
    if (s > pos) out.push(<span key={`t${i}`}>{text.slice(pos, s)}</span>);
    out.push(
      <mark key={`m${i}`} className="dr-mark" title={m.text}>
        {text.slice(s, e)}
      </mark>,
    );
    pos = e;
  });
  if (pos < text.length) out.push(<span key="tail">{text.slice(pos)}</span>);
  return out;
}
