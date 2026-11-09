"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Icon from "@/components/Icon";
import { useSpeech } from "@/components/useSpeech";
import {
  currentVersion,
  diffStats,
  diffText,
  paragraphAt,
  paragraphs,
  type DraftComment,
  type DraftVersion,
  type Paragraph,
  type ReviseRequest,
} from "@/lib/draftCore";

type Draft = {
  id: string;
  case_name: string;
  recipient: string;
  channel: string;
  status: "open" | "done" | "dropped";
  context: string | null;
  versions: DraftVersion[];
  pending_comments: DraftComment[];
  revise_request: ReviseRequest | null;
  updated_at: string;
};

/** ダメ出しの宛先。選んだ文字 > 押した段落 > 話している間に画面の真ん中にある段落 */
type Target = { kind: "selection" | "paragraph"; quote: string; start: number; end: number } | null;
type View = "text" | "diff" | "edit";

function newId(): string {
  const a = new Uint8Array(8);
  crypto.getRandomValues(a);
  return Array.from(a, (x) => x.toString(16).padStart(2, "0")).join("");
}

/**
 * 事例3（フィードバックループ）の第1段: 読みながら、箇所を決めて声で指摘 → 1件ずつその場で記録。
 * たまったら「まとめて直す」→ Mac の Cursor（定額）が書き直す → 差分で確かめる。
 */
export default function DraftReviewClient({ id }: { id: string }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const [toast, setToast] = useState("");
  const [view, setView] = useState<View>("text");
  const [target, setTarget] = useState<Target>(null);
  const [typed, setTyped] = useState("");
  const [editText, setEditText] = useState("");
  const [compareTo, setCompareTo] = useState("");
  const [focusPara, setFocusPara] = useState(-1); // 話している間の「画面の真ん中」
  const textRef = useRef<HTMLDivElement>(null);
  const draftRef = useRef<Draft | null>(null);
  draftRef.current = draft;
  const targetRef = useRef<Target>(null);
  targetRef.current = target;
  const segStartRef = useRef<{ t: number; target: Target; para: number } | null>(null);
  const queueRef = useRef<Promise<unknown>>(Promise.resolve());

  const cur = useMemo(() => (draft ? currentVersion(draft.versions) : null), [draft]);
  const paras = useMemo(() => (cur ? paragraphs(cur.text) : []), [cur]);
  const parasRef = useRef<Paragraph[]>([]);
  parasRef.current = paras;
  const pending = draft?.pending_comments || [];
  const rr = draft?.revise_request || null;
  const working = rr?.status === "queued" || rr?.status === "running";

  const load = useCallback(async () => {
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

  // Mac が直している間は見に行く
  useEffect(() => {
    if (!working) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [working, load]);

  /** 画面の真ん中にある段落 */
  const centerPara = useCallback((): number => {
    const box = textRef.current;
    if (!box) return -1;
    const mid = window.innerHeight * 0.4;
    let best = -1;
    let bestD = Infinity;
    box.querySelectorAll<HTMLElement>("[data-p]").forEach((el) => {
      const r = el.getBoundingClientRect();
      const d = r.top <= mid && r.bottom >= mid ? 0 : Math.min(Math.abs(r.top - mid), Math.abs(r.bottom - mid));
      if (d < bestD) {
        bestD = d;
        best = Number(el.dataset.p);
      }
    });
    return best;
  }, []);

  async function post(body: Record<string, unknown>, label = "") {
    if (label) setBusy(label);
    setErr("");
    try {
      const r = await fetch(`/api/drafts/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
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
      if (label) setBusy("");
    }
  }

  /** 1件ずつ順番に保存（声は続けて届くので、並べて送る） */
  function saveComment(c: DraftComment) {
    // 先に画面へ出す（保存は後ろで）
    setDraft((d) => (d ? { ...d, pending_comments: [...(d.pending_comments || []), c] } : d));
    queueRef.current = queueRef.current.then(() => post({ op: "comment", comment: c }));
  }

  function commentFor(text: string, via: "voice" | "typed", t?: { start: number; end: number }, snap?: { target: Target; para: number }) {
    const tg = snap ? snap.target : targetRef.current;
    const ps = parasRef.current;
    let c: DraftComment;
    if (tg) {
      c = { id: newId(), quote: tg.quote, start: tg.start, end: tg.end, text, via, target: tg.kind };
    } else {
      const pi = snap ? snap.para : centerPara();
      const p = ps[pi];
      c = p
        ? { id: newId(), quote: p.text, start: p.start, end: p.end, text, via, target: "viewport" }
        : { id: newId(), quote: "", start: null, end: null, text, via, target: "whole" };
    }
    if (t) {
      c.t_start = t.start;
      c.t_end = t.end;
    }
    c.version = currentVersion(draftRef.current?.versions || [])?.label;
    return c;
  }

  const speech = useSpeech(
    useCallback(
      (text: string) => {
        const s = segStartRef.current;
        segStartRef.current = null;
        saveComment(commentFor(text, "voice", { start: s?.t ?? Date.now(), end: Date.now() }, s ? { target: s.target, para: s.para } : undefined));
      },
      // eslint-disable-next-line react-hooks/exhaustive-deps
      [],
    ),
  );

  // 話し始めた瞬間の箇所を覚える（話し終わる頃にスクロールしていても、話し始めの箇所に付ける）
  useEffect(() => {
    if (speech.interim && !segStartRef.current) {
      segStartRef.current = { t: Date.now(), target: targetRef.current, para: targetRef.current ? -1 : centerPara() };
    }
  }, [speech.interim, centerPara]);

  // 話している間は、どの段落に付くかを見せる
  useEffect(() => {
    if (!speech.listening || target) {
      setFocusPara(-1);
      return;
    }
    const h = () => setFocusPara(centerPara());
    h();
    window.addEventListener("scroll", h, { passive: true });
    return () => window.removeEventListener("scroll", h);
  }, [speech.listening, target, centerPara]);

  function captureSelection() {
    const box = textRef.current;
    const s = window.getSelection();
    if (!box || !s || s.rangeCount === 0 || s.isCollapsed) return false;
    const r = s.getRangeAt(0);
    if (!box.contains(r.startContainer) || !box.contains(r.endContainer)) return false;
    const pre = document.createRange();
    pre.selectNodeContents(box);
    pre.setEnd(r.startContainer, r.startOffset);
    // 段落の間の改行は DOM に無いので、段落の位置から数え直す
    const startEl = (r.startContainer.nodeType === 1 ? (r.startContainer as Element) : r.startContainer.parentElement)?.closest<HTMLElement>("[data-p]");
    const quote = r.toString();
    if (!quote.trim() || !startEl) return false;
    const p = parasRef.current[Number(startEl.dataset.p)];
    if (!p) return false;
    const inPara = document.createRange();
    inPara.selectNodeContents(startEl);
    inPara.setEnd(r.startContainer, r.startOffset);
    const start = p.start + inPara.toString().length;
    setTarget({ kind: "selection", quote, start, end: start + quote.length });
    return true;
  }

  useEffect(() => {
    const h = () => {
      if (view === "text") captureSelection();
    };
    document.addEventListener("selectionchange", h);
    return () => document.removeEventListener("selectionchange", h);
  }, [view]);

  function tapPara(p: Paragraph) {
    const s = window.getSelection();
    if (s && !s.isCollapsed) return; // 文字を選んでいるときは選択を優先
    if (target?.kind === "paragraph" && target.start === p.start) setTarget(null);
    else setTarget({ kind: "paragraph", quote: p.text, start: p.start, end: p.end });
  }

  function addTyped() {
    const t = typed.trim();
    if (!t) return;
    saveComment(commentFor(t, "typed"));
    setTyped("");
  }

  async function reviseAll() {
    if (speech.listening) speech.stop();
    await queueRef.current; // 保存待ちのダメ出しを先に
    const j = await post({ op: "revise" }, "直しに回しています…");
    if (j) {
      setTarget(null);
      setToast("まとめて直しに回しました。Mac の Cursor が直します（1〜2分）");
    }
  }

  async function saveManual() {
    const j = await post({ op: "manual", text: editText, updatedAt: draft?.updated_at }, "保存しています…");
    if (j) {
      setView("diff");
      setToast("手直しを保存しました");
    }
  }

  async function revert() {
    if (!confirm("いまの版を戻して、1つ前の版に戻しますか？（記録は残ります）")) return;
    if (await post({ op: "revert", updatedAt: draft?.updated_at }, "戻しています…")) setToast("1つ前の版に戻しました");
  }

  async function done() {
    const j = await post({ op: "done", updatedAt: draft?.updated_at }, "確定しています…");
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

  // 新しい版ができたら差分を見せる
  const live = useMemo(() => (draft ? draft.versions.filter((v) => !v.reverted) : []), [draft]);
  const lastLabel = cur?.label;
  useEffect(() => {
    if (live.length >= 2) setView("diff");
    setCompareTo("");
  }, [lastLabel]); // eslint-disable-line react-hooks/exhaustive-deps
  const prev = useMemo(() => {
    if (!cur || live.length < 2) return null;
    if (compareTo) return live.find((v) => v.label === compareTo && v !== cur) || null;
    return live[live.length - 2];
  }, [cur, live, compareTo]);
  const segs = useMemo(() => (cur && prev ? diffText(prev.text, cur.text) : []), [cur, prev]);
  const stats = useMemo(() => diffStats(segs), [segs]);

  if (err && !draft) return <div className="card warn">{err}</div>;
  if (!draft || !cur) return <div className="card meta">読み込み中…</div>;

  const open = draft.status === "open";
  // 段落ごとのダメ出し（この版へのもの）
  const byPara = new Map<number, DraftComment[]>();
  const whole: DraftComment[] = [];
  for (const c of pending) {
    const pi = c.start !== null && c.version === cur.label ? paragraphAt(paras, c.start) : -1;
    if (pi < 0) whole.push(c);
    else byPara.set(pi, [...(byPara.get(pi) || []), c]);
  }
  const targetLabel = target
    ? `${target.kind === "selection" ? "選んだ所" : "この段落"}：「${target.quote.slice(0, 40)}${target.quote.length > 40 ? "…" : ""}」`
    : speech.listening
      ? "画面の真ん中の段落に付けます（スクロールで切り替え）"
      : "段落を押すか、文字をなぞって選ぶ。選ばなければ、話している所の段落に付きます";

  return (
    <div className="list dr">
      <div className="card dr-head">
        <div className="eyebrow">
          {draft.recipient} ／ {draft.channel} ／ {open ? "直し中" : "確定済み"}
        </div>
        <strong>{draft.case_name}</strong>
        <div className="dr-versions">
          {draft.versions.map((v) => (
            <span key={v.label} className={`pill ${v === cur ? "on" : ""} ${v.reverted ? "off" : ""}`}>
              {v.label}
              {v.by === "ai" ? "・AI" : v.by === "owner" ? "・手" : ""}
            </span>
          ))}
        </div>
      </div>

      {rr && rr.status !== "done" ? (
        <div className={`card dr-status ${rr.status}`}>
          {rr.status === "queued" ? <>直し待ち（{rr.comments.length}件）… Mac の Cursor が拾います</> : null}
          {rr.status === "running" ? <>Mac の Cursor が直しています（{rr.comments.length}件）…</> : null}
          {rr.status === "error" ? <>直せませんでした：{rr.error}</> : null}
          <div className="btn-row">
            {rr.status === "error" ? <button onClick={() => post({ op: "retry" }, "やり直しています…")}>もう一度</button> : null}
            {rr.status !== "running" ? <button onClick={() => post({ op: "cancel" }, "戻しています…")}>取り消してダメ出しに戻す</button> : null}
          </div>
        </div>
      ) : null}

      <div className="tabs dr-tabs" role="tablist">
        <button className={`tab ${view === "text" ? "active" : ""}`} onClick={() => setView("text")} role="tab">
          読んでダメ出し{pending.length ? `（${pending.length}）` : ""}
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
          <div ref={textRef} className="dr-paras" onMouseUp={() => captureSelection()} onTouchEnd={() => captureSelection()}>
            {paras.map((p) => {
              const cs = byPara.get(p.index) || [];
              const on = target?.kind === "paragraph" && target.start === p.start;
              const sel = target?.kind === "selection" && target.start >= p.start && target.start <= p.end;
              return (
                <div key={p.index} className={`dr-para ${on || sel ? "on" : ""} ${focusPara === p.index ? "focus" : ""}`}>
                  <p data-p={p.index} onClick={() => open && tapPara(p)}>
                    {p.text}
                  </p>
                  {cs.length ? (
                    <div className="dr-pcomments">
                      {cs.map((c) => (
                        <CommentLine key={c.id} c={c} showQuote={c.target === "selection"} onDelete={() => c.id && post({ op: "uncomment", commentId: c.id })} />
                      ))}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
          {whole.length ? (
            <div className="dr-pcomments">
              <div className="eyebrow">全体・前の版へのダメ出し</div>
              {whole.map((c) => (
                <CommentLine key={c.id} c={c} showQuote onDelete={() => c.id && post({ op: "uncomment", commentId: c.id })} />
              ))}
            </div>
          ) : null}
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
                <div key={c.id || i} className="meta">
                  {c.via === "voice" ? "🎤" : "✎"} {c.quote ? `「${c.quote.slice(0, 40)}」` : "全体"}：{c.text}
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

      {open && view === "text" ? (
        <div className={`card dr-dock ${speech.listening ? "live" : ""}`}>
          <div className="dr-target meta">
            <span className="grow">{targetLabel}</span>
            {target ? (
              <button className="linkbtn" onClick={() => setTarget(null)}>
                外す
              </button>
            ) : null}
          </div>
          {speech.listening && speech.interim ? <div className="dr-interim">{speech.interim}</div> : null}
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
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && typed.trim()) {
                  e.preventDefault();
                  addTyped();
                }
              }}
              placeholder={speech.supported ? "マイクで話す（区切るごとに1件ずつ残ります）か、ここに書く" : "ここにダメ出しを書く（このブラウザは音声入力に未対応）"}
              rows={2}
            />
          </div>
          {speech.error ? <div className="warn">{speech.error}</div> : null}
          <div className="btn-row">
            <button onClick={addTyped} disabled={!typed.trim()}>
              書いて追加<span className="dr-kbd">⌘/Ctrl+Enter</span>
            </button>
            <button className="primary" onClick={reviseAll} disabled={!!busy || working || !pending.length}>
              まとめて直す{pending.length ? `（${pending.length}件）` : ""}
            </button>
          </div>
        </div>
      ) : null}

      {busy ? <div className="card meta">{busy}</div> : null}
      {err ? <div className="card warn">{err}</div> : null}

      <div className="btn-row">
        <button onClick={copy}>いまの文面をコピー</button>
        {open && live.length >= 2 ? <button onClick={revert}>1つ前に戻す</button> : null}
        {open ? (
          <button className="primary" onClick={done} disabled={!!busy || working}>
            これで確定（コピー）
          </button>
        ) : (
          <button onClick={() => post({ op: "reopen", updatedAt: draft.updated_at }, "開き直しています…")}>もう一度直す</button>
        )}
      </div>

      {toast ? <div className="desk-toast">{toast}</div> : null}
    </div>
  );
}

function CommentLine({ c, showQuote, onDelete }: { c: DraftComment; showQuote?: boolean; onDelete: () => void }) {
  return (
    <div className="dr-comment">
      <span className="meta">{c.via === "voice" ? "🎤" : "✎"}</span>
      <span className="grow">
        {showQuote && c.quote ? <span className="meta">「{c.quote.slice(0, 30)}{c.quote.length > 30 ? "…" : ""}」 </span> : null}
        {c.text}
      </span>
      <button className="linkbtn" style={{ whiteSpace: "nowrap" }} onClick={onDelete}>
        消す
      </button>
    </div>
  );
}
