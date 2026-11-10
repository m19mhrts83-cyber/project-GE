"use client";

import { useState } from "react";
import {
  DECISION_TAGS,
  type DecisionNote,
  type DecisionTagKind,
} from "@/lib/kurashiftDecision";

/**
 * お金の判断の直前に出す「判断メモ」（ループウェア型）。
 * 理由は任意。押さずに「決める」でも判断は記録される。
 * 「次も同じに」は基準の候補になるだけで、ルールにするかは週次レビューで松野さんが決める。
 */
export default function DecisionNotePanel({
  title,
  hint,
  tagKind,
  confirmLabel,
  busy,
  onConfirm,
  onCancel,
}: {
  title: string;
  hint?: string;
  tagKind: DecisionTagKind;
  confirmLabel: string;
  busy?: boolean;
  onConfirm: (note: DecisionNote) => void;
  onCancel: () => void;
}) {
  const [tags, setTags] = useState<string[]>([]);
  const [note, setNote] = useState("");
  const [always, setAlways] = useState(false);
  const options = DECISION_TAGS[tagKind];

  function toggle(key: string) {
    setTags((cur) =>
      cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]
    );
  }

  return (
    <div className="decision-note" role="dialog" aria-label={title}>
      <div className="decision-note-title">{title}</div>
      {hint ? <p className="decision-note-hint">{hint}</p> : null}
      <div className="decision-note-label">理由（任意・複数可）</div>
      <div className="decision-note-tags">
        {options.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`chip${tags.includes(t.key) ? " on" : ""}`}
            aria-pressed={tags.includes(t.key)}
            onClick={() => toggle(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <input
        type="text"
        className="decision-note-input"
        placeholder="ひとこと（任意）"
        value={note}
        maxLength={400}
        onChange={(e) => setNote(e.target.value)}
      />
      <label className="decision-note-scope">
        <input
          type="checkbox"
          checked={always}
          onChange={(e) => setAlways(e.target.checked)}
        />
        次も同じ考えで判断する（基準の候補にする）
      </label>
      <div className="decision-note-actions">
        <button
          type="button"
          className="btn primary"
          disabled={busy}
          onClick={() =>
            onConfirm({
              reason_tags: tags,
              note: note.trim() || null,
              scope: always ? "always" : "once",
            })
          }
        >
          {busy ? "…" : confirmLabel}
        </button>
        <button type="button" className="btn" disabled={busy} onClick={onCancel}>
          やめる
        </button>
      </div>
      <p className="decision-note-foot">
        判断ログに残り、週1のレビューで見返します。
      </p>
    </div>
  );
}
