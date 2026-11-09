"use client";

import { useEffect, useRef, useState } from "react";
import Icon from "./Icon";
import { useSpeech } from "./useSpeech";
import type { VoiceComment } from "@/lib/storage";

type T = { id: string; label: string };

/** いま画面で見ているカード（data-tid を持つ要素のうち、画面上部寄りの基準線に最も近いもの） */
function useViewed(): T | null {
  const [v, setV] = useState<T | null>(null);
  useEffect(() => {
    const compute = () => {
      const els = Array.from(document.querySelectorAll<HTMLElement>("[data-tid]"));
      if (!els.length) {
        setV(null);
        return;
      }
      const line = window.innerHeight * 0.35;
      let best: HTMLElement | null = null;
      let bd = Infinity;
      for (const el of els) {
        const r = el.getBoundingClientRect();
        const d = r.top <= line && r.bottom >= line ? 0 : Math.min(Math.abs(r.top - line), Math.abs(r.bottom - line));
        if (d < bd) {
          bd = d;
          best = el;
        }
      }
      if (best) {
        const id = best.dataset.tid || "";
        const label = best.dataset.tlabel || "";
        setV((p) => (p && p.id === id && p.label === label ? p : { id, label }));
      }
    };
    compute();
    window.addEventListener("scroll", compute, { passive: true });
    window.addEventListener("resize", compute);
    const iv = window.setInterval(compute, 400);
    return () => {
      window.removeEventListener("scroll", compute);
      window.removeEventListener("resize", compute);
      window.clearInterval(iv);
    };
  }, []);
  return v;
}

/**
 * 見ながら言う（T05）。固定バーの上段に置く。
 * - 既定は「見ている所に追従」：スクロールして今見ているカードが対象になる
 * - 話し始めた時点に見ていたカードへ結び付ける（話している間にスクロールしても、前のカードの話は前のカードに残る）
 * - カードをタップすると「固定」。追従に戻すボタンもある
 * - 話し終えたときに見ている場所が違っていたら、コメントに「こちらへ移す」が出る
 */
export default function VoiceDock({
  onComment,
}: {
  onComment: (
    text: string,
    targetId: string,
    targetLabel: string,
    via: "voice" | "text",
    meta?: { startedAt?: string; mode?: "follow" | "pin"; alt?: T },
  ) => void;
}) {
  const viewed = useViewed();
  const [mode, setMode] = useState<"follow" | "pin">("follow");
  const [pinned, setPinned] = useState<T | null>(null);
  const cur: T | null = mode === "pin" ? pinned : (viewed ?? pinned);
  const curRef = useRef<T | null>(cur);
  curRef.current = cur;

  // カードをタップしたら、そのカードに固定する（バーの中のタップは無視）
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      const el = e.target as HTMLElement | null;
      if (!el || el.closest(".bar")) return;
      const card = el.closest<HTMLElement>("[data-tid]");
      if (!card) return;
      setPinned({ id: card.dataset.tid || "", label: card.dataset.tlabel || "" });
      setMode("pin");
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, []);

  const [flash, setFlash] = useState<{ text: string; label: string; moved: boolean } | null>(null);
  const [typed, setTyped] = useState("");
  // 話し始めた時点の対象と時刻
  const startRef = useRef<{ t: T; at: string } | null>(null);

  const speech = useSpeech((text) => {
    const start = startRef.current ?? (curRef.current ? { t: curRef.current, at: new Date().toISOString() } : null);
    startRef.current = null;
    if (!start) return;
    const end = curRef.current;
    const moved = !!end && end.id !== start.t.id;
    onComment(text, start.t.id, start.t.label, "voice", {
      startedAt: start.at,
      mode,
      alt: moved && end ? end : undefined,
    });
    setFlash({ text, label: start.t.label, moved });
  });

  // 話し始め（字幕が出始めた瞬間）の場所と時刻を控える
  useEffect(() => {
    if (speech.interim && !startRef.current && curRef.current) {
      startRef.current = { t: curRef.current, at: new Date().toISOString() };
    }
  }, [speech.interim]);

  useEffect(() => {
    if (!flash) return;
    const t = window.setTimeout(() => setFlash(null), 4000);
    return () => window.clearTimeout(t);
  }, [flash]);

  const { listening } = speech;
  // 字幕に紐づく対象：話している間は「話し始めた場所」、それ以外は「いま見ている場所」
  const shown = listening && startRef.current ? startRef.current.t : cur;
  const noTarget = !cur;

  return (
    <div className={`vdock ${listening ? "live" : ""}`}>
      <div className="vdock-row">
        {speech.supported ? (
          <button
            type="button"
            className="vmic"
            aria-pressed={listening}
            aria-label={listening ? "音声入力を止める" : "見ながら声でフィードバックする"}
            disabled={noTarget}
            onClick={() => (listening ? speech.stop() : speech.start())}
          >
            <Icon name={listening ? "stop" : "mic"} size={20} stroke={2.4} />
          </button>
        ) : null}
        <div className="vcap" aria-live="polite">
          <div className="vcap-target">
            {listening ? <span className="vdot" aria-hidden="true" /> : null}
            {!shown ? (
              "カードを見ながら話すと、見ているカードに結び付きます"
            ) : (
              <>
                <span>{listening ? "聞いています" : mode === "follow" ? "見ている" : "固定"}</span>
                <strong>{shown.label}</strong>
              </>
            )}
          </div>
          <div className="vcap-text">
            {speech.error ? (
              <span className="verr">{speech.error}</span>
            ) : listening ? (
              speech.interim ? (
                <span className="vinterim">{speech.interim}</span>
              ) : (
                <span className="vhint">話してください。話し始めた時点に見ているカードへ残ります</span>
              )
            ) : flash ? (
              <span className="vfinal">
                <Icon name="check" size={14} stroke={3} /> {flash.text}
                {flash.moved ? <small className="vmoved"> 話し始めた場所に残しました</small> : null}
              </span>
            ) : speech.supported ? (
              <span className="vhint">マイクを押して、画面を見ながら話す。字幕が出て、そのカードのコメントとして残ります</span>
            ) : (
              <span className="vhint">この端末は音声認識に未対応です。文字で残せます</span>
            )}
          </div>
        </div>
      </div>
      <div className="vmode" role="group" aria-label="対象の決め方">
        <button
          type="button"
          className={mode === "follow" ? "on" : ""}
          aria-pressed={mode === "follow"}
          onClick={() => setMode("follow")}
        >
          見ている所に追従
        </button>
        <button
          type="button"
          className={mode === "pin" ? "on" : ""}
          aria-pressed={mode === "pin"}
          disabled={!pinned}
          onClick={() => setMode("pin")}
        >
          タップしたカードに固定
        </button>
      </div>
      {!speech.supported ? (
        <form
          className="vtype"
          onSubmit={(e) => {
            e.preventDefault();
            if (!cur || !typed.trim()) return;
            onComment(typed, cur.id, cur.label, "text", { mode, startedAt: new Date().toISOString() });
            setFlash({ text: typed.trim(), label: cur.label, moved: false });
            setTyped("");
          }}
        >
          <input
            type="text"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder="キーボードの音声入力でもOK"
            aria-label="コメント"
            disabled={noTarget}
          />
          <button type="submit" className="secondary" disabled={noTarget || !typed.trim()}>
            残す
          </button>
        </form>
      ) : null}
    </div>
  );
}

/** カードの下に出す、そのカードへのコメント一覧（時刻・保存状態つき）。 */
export function CommentList({
  comments,
  onDelete,
  onMove,
}: {
  comments: VoiceComment[];
  onDelete: (id: string) => void;
  onMove?: (id: string, targetId: string, targetLabel: string) => void;
}) {
  if (!comments.length) return null;
  return (
    <ul className="vlist" aria-label="このカードへのコメント">
      {comments.map((c) => (
        <li key={c.id}>
          <Icon name={c.via === "voice" ? "mic" : "list"} size={14} />
          <span className="vtext">
            {c.text}
            {c.alt && onMove ? (
              <button
                type="button"
                className="vmove"
                onClick={() => onMove(c.id, c.alt!.id, c.alt!.label)}
              >
                「{c.alt.label.slice(0, 14)}」の話なら移す
              </button>
            ) : null}
          </span>
          <span className="vmeta mono">{hhmm(c.startedAt || c.at)}</span>
          <span
            className={`vsync ${c.synced === true ? "ok" : c.synced === false ? "local" : ""}`}
            title={
              c.synced === true
                ? "Supabase の判断ログに保存済み"
                : c.synced === false
                  ? "端末のみ（サーバ未接続）"
                  : "送信中"
            }
          >
            {c.synced === true ? "ログ保存" : c.synced === false ? "端末のみ" : "送信中"}
          </span>
          <button type="button" className="vdel" aria-label="このコメントを消す" onClick={() => onDelete(c.id)}>
            <Icon name="x" size={14} />
          </button>
        </li>
      ))}
    </ul>
  );
}

function hhmm(iso: string) {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}`;
}
