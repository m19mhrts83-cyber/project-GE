"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  DECISION_TAGS,
  type DecisionNote,
  type DecisionTagKind,
} from "@/lib/kurashiftDecision";
import type { DecisionHints } from "@/lib/kurashiftDecisionLog";

/**
 * お金の判断の直前に出す「判断メモ」（ループウェア型）。
 *
 * - 理由は任意。何も押さずに決めても判断は記録される（T02 理由タグ・T03 一言）
 * - 同じ種類の過去の判断を引いて、よく使う理由を前に並べ、「前回と同じ」をワンタップにする（L09）。
 *   AI が理由を推測して埋めることはしない。出すのは本人の過去の記録だけ
 * - 「次も同じに」は、同じ理由が2回目になったときだけ聞く（T09・L03）
 * - 開いてから決めるまでの時間を残す（L11 判断しにくさ）
 */

const hintCache = new Map<string, DecisionHints>();

function shortDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo",
    month: "numeric",
    day: "numeric",
  }).format(d);
}

export default function DecisionNotePanel({
  title,
  hint,
  tagKind,
  ctx,
  confirmLabel,
  tone = "go",
  busy,
  onConfirm,
  onCancel,
}: {
  title: string;
  hint?: string;
  tagKind: DecisionTagKind;
  /** 同じ種類の判断をまとめる鍵（例: money:approved / deal:pass）。過去の判断を引くのに使う */
  ctx: string;
  confirmLabel: string;
  /** go＝進める判断、stop＝見送り・取消、hold＝相談に回す */
  tone?: "go" | "stop" | "hold";
  busy?: boolean;
  onConfirm: (note: DecisionNote) => void;
  onCancel: () => void;
}) {
  const [tags, setTags] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [always, setAlways] = useState(false);
  const [hints, setHints] = useState<DecisionHints | null>(hintCache.get(ctx) || null);
  const [mounted, setMounted] = useState(false);
  const openedAt = useRef(Date.now());
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setMounted(true);
    let alive = true;
    fetch(`/api/decisions/hints?ctx=${encodeURIComponent(ctx)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (alive && d?.hints) {
          hintCache.set(ctx, d.hints as DecisionHints);
          setHints(d.hints as DecisionHints);
        }
      })
      .catch(() => {
        /* ヒントが無くても判断はできる */
      });
    return () => {
      alive = false;
    };
  }, [ctx]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !busy) onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onCancel]);

  // よく使う理由を前に（使った回数の多い順）。使ったことのない理由は元の並び
  const options = useMemo(() => {
    const base = DECISION_TAGS[tagKind];
    const count = new Map((hints?.tagCounts || []).map((t) => [t.key, t.count]));
    return [...base]
      .map((t, i) => ({ ...t, count: count.get(t.key) || 0, i }))
      .sort((a, b) => b.count - a.count || a.i - b.i);
  }, [tagKind, hints]);

  const allowed = useMemo(() => new Set(DECISION_TAGS[tagKind].map((t) => t.key)), [tagKind]);
  const last = hints?.last || null;
  const lastTags = (last?.reasonTags || []).filter((t) => allowed.has(t));
  const suggested = useMemo(
    () => Array.from(new Set([...lastTags, ...options.filter((o) => o.count > 0).map((o) => o.key)])).slice(0, 6),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [hints, options]
  );
  const alwaysSet = new Set(hints?.alwaysTags || []);
  // 同じ理由が2回目以降で、まだ「次も同じに」にしていないものがあれば範囲を聞く
  const repeat = tags.filter(
    (t) => (options.find((o) => o.key === t)?.count || 0) >= 1 && !alwaysSet.has(t)
  );
  const repeatLabels = repeat
    .map((t) => options.find((o) => o.key === t)?.label || t)
    .join("・");

  function toggle(key: string) {
    setTags((cur) => (cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]));
  }

  function submit(over?: Partial<DecisionNote>) {
    if (busy) return;
    hintCache.delete(ctx); // 次に開いたときは今回の判断も入れて引き直す
    onConfirm({
      reason_tags: tags,
      note: note.trim() || null,
      scope: always && repeat.length ? "always" : "once",
      decide_ms: Date.now() - openedAt.current,
      suggested_tags: suggested,
      same_as_last: false,
      ...over,
    });
  }

  const body = (
    <div
      className="dn-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onCancel();
      }}
    >
      <div className={`dn-sheet tone-${tone}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="dn-grip" aria-hidden />
        <div className="dn-kicker">判断メモ</div>
        <h2 className="dn-title">{title}</h2>
        {hint ? <p className="dn-hint">{hint}</p> : null}

        {hints?.regrets.length ? (
          <div className="dn-caution">
            <strong>前の答え合わせ</strong>
            {hints.regrets.map((r) => (
              <div key={r.at}>
                {shortDate(r.at)}「{r.title}」は「やり直したい」でした
                {r.note ? `：${r.note}` : ""}
              </div>
            ))}
          </div>
        ) : null}

        {last && (lastTags.length || last.note) ? (
          <button
            type="button"
            className="dn-last"
            disabled={busy}
            onClick={() =>
              submit({ reason_tags: lastTags, note: last.note, scope: "once", same_as_last: true })
            }
          >
            <span className="dn-last-label">前回と同じ理由で決める</span>
            <span className="dn-last-body">
              {shortDate(last.at)}「{last.title}」
              {lastTags.length
                ? `　${options
                    .filter((o) => lastTags.includes(o.key))
                    .map((o) => o.label)
                    .join("・")}`
                : ""}
              {last.note ? `　“${last.note}”` : ""}
            </span>
          </button>
        ) : null}

        <div className="dn-label">
          理由<span>任意・いくつでも</span>
        </div>
        <div className="dn-tags">
          {options.map((t) => (
            <button
              key={t.key}
              type="button"
              className={`dn-chip${tags.includes(t.key) ? " on" : ""}`}
              aria-pressed={tags.includes(t.key)}
              onClick={() => toggle(t.key)}
            >
              {t.label}
              {t.count > 0 ? <span className="dn-chip-count">{t.count}</span> : null}
            </button>
          ))}
        </div>

        <input
          ref={inputRef}
          type="text"
          className="dn-input"
          placeholder="次に覚えておくことは？（任意）"
          value={note}
          maxLength={400}
          onChange={(e) => setNote(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.nativeEvent.isComposing) submit();
          }}
        />

        {repeat.length ? (
          <div className="dn-scope">
            <div className="dn-scope-q">
              「{repeatLabels}」は前にも選んでいます。次も同じ考えで判断しますか？
            </div>
            <div className="dn-seg" role="radiogroup">
              <button
                type="button"
                role="radio"
                aria-checked={!always}
                className={!always ? "on" : ""}
                onClick={() => setAlways(false)}
              >
                今回だけ
              </button>
              <button
                type="button"
                role="radio"
                aria-checked={always}
                className={always ? "on" : ""}
                onClick={() => setAlways(true)}
              >
                次も同じに
              </button>
            </div>
          </div>
        ) : null}

        <div className="dn-actions">
          <button type="button" className="dn-cancel" disabled={busy} onClick={onCancel}>
            やめる
          </button>
          <button type="button" className="dn-confirm" disabled={busy} onClick={() => submit()}>
            {busy ? "記録中…" : confirmLabel}
          </button>
        </div>
        <p className="dn-foot">
          {hints && hints.count > 0
            ? `過去 ${hints.count} 件の同じ種類の判断から並べています。`
            : "理由を残すと、次からここに「前回と同じ」が出ます。"}
          基準にするかは週1のレビューで決めます。
        </p>
      </div>
    </div>
  );

  if (!mounted) return null;
  return createPortal(body, document.body);
}
