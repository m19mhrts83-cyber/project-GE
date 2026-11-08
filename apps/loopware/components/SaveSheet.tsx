"use client";

import { useEffect, useState } from "react";
import Icon from "./Icon";
import { formatDecisionMd, loadStore, type DecisionRecord } from "@/lib/storage";

export type SaveLine = { k: string; v: string };
export type SaveStatus = "pending" | "server" | "local";

/**
 * 決定を保存した瞬間の演出。
 * 判断の中身が1行ずつログへ流れ込む → 件数が増える → 「改善に使える形で保存した」と示す。
 * 「◯件で賢くなった」のような精度表示はしない（件数はログの数として見せるだけ）。
 */
export default function SaveSheet({
  rec,
  decisionLabel,
  lines,
  total,
  status,
  onClose,
  onUndo,
  closeLabel = "閉じる",
}: {
  rec: DecisionRecord;
  decisionLabel: string;
  lines: SaveLine[];
  total: number;
  status: SaveStatus;
  onClose: () => void;
  onUndo?: () => void;
  closeLabel?: string;
}) {
  const stepMs = 260;
  const base = 450; // 最初の行が出るまで
  const countAt = base + lines.length * stepMs + 200;
  const doneAt = countAt + 700;

  const [shown, setShown] = useState(total - 1);
  const [copied, setCopied] = useState(false);
  const [past, setPast] = useState<DecisionRecord[]>([]);

  useEffect(() => {
    setPast(
      loadStore()
        .decisions.filter((d) => !(d.topicId === rec.topicId && d.agentId === rec.agentId))
        .slice(0, 3),
    );
  }, [rec]);

  useEffect(() => {
    const t = window.setTimeout(() => setShown(total), countAt);
    return () => window.clearTimeout(t);
  }, [total, countAt]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="sheet-wrap" role="dialog" aria-modal="true" aria-label="判断ログを保存しました">
      <div className="sheet-dim" onClick={onClose} />
      <div className="sheet">
        <div className="sheet-head">
          <span className="sheet-ring" aria-hidden="true">
            <Icon name="check" size={22} stroke={3} />
          </span>
          <div>
            <div className="eyebrow acc" style={{ color: "var(--positive)" }}>
              SAVED
            </div>
            <div className="sheet-title">{decisionLabel}</div>
          </div>
        </div>

        <ul className="log-lines" aria-label="保存したログ">
          {lines.map((l, i) => (
            <li
              key={l.k}
              className="log-line"
              style={{ animationDelay: `${base + i * stepMs}ms` }}
            >
              <span className="log-k">{l.k}</span>
              <span className="log-v">{l.v}</span>
              <span
                className="log-tick"
                style={{ animationDelay: `${base + i * stepMs + 180}ms` }}
              >
                <Icon name="check" size={12} stroke={3.5} />
              </span>
            </li>
          ))}
        </ul>

        <div className="log-count" style={{ animationDelay: `${countAt - 150}ms` }}>
          <span className="meta">判断ログ</span>
          <span className="mono count-num">
            <span key={shown} className="count-pop">
              {shown}
            </span>
            <small> 件</small>
          </span>
          <span className="count-plus mono" style={{ animationDelay: `${countAt}ms` }}>
            +1
          </span>
        </div>

        <ol className="log-stack" aria-label="ログの積み上がり" style={{ animationDelay: `${countAt}ms` }}>
          <li className="stack-new" style={{ animationDelay: `${countAt}ms` }}>
            <span className="mono">{hhmm(rec.decidedAt)}</span>
            <span>{rec.agentId} · {decisionLabel}</span>
            <span className="stack-badge">NEW</span>
          </li>
          {past.map((r, i) => (
            <li key={`${r.topicId}-${r.decidedAt}`} className="stack-old" style={{ animationDelay: `${countAt + 120 + i * 90}ms` }}>
              <span className="mono">{hhmm(r.decidedAt)}</span>
              <span>{r.agentId} · {r.finalText ? r.finalText.split("\n")[0].slice(0, 28) : r.topicId}</span>
            </li>
          ))}
        </ol>

        <div className="layers" style={{ animationDelay: `${doneAt - 100}ms` }}>
          <div className="layer on">
            <Icon name="check" size={14} stroke={3} />
            生の判断<small>保存済み</small>
          </div>
          <div className="layer">
            AIの解釈<small>まだ作らない</small>
          </div>
          <div className="layer">
            承認した基準<small>確認するまで入れない</small>
          </div>
        </div>

        <div className="ready" style={{ animationDelay: `${doneAt}ms` }}>
          <div className="ready-title">
            <Icon name="check" size={16} stroke={3} />
            改善に使える形で保存しました
          </div>
          <div className="meta">
            {status === "pending" && "サーバへ送っています…"}
            {status === "server" && "端末とサーバ（判断ログ）の両方に保存"}
            {status === "local" && "この端末に保存。サーバ未接続のため、送信は保留です"}
            ・今回だけの判断として記録（基準にはしていません）
          </div>
        </div>

        <div className="sheet-actions" style={{ animationDelay: `${doneAt + 150}ms` }}>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              void navigator.clipboard.writeText(formatDecisionMd(rec));
              setCopied(true);
            }}
          >
            {copied ? "コピーした" : "AIに渡すMDをコピー"}
          </button>
          <button type="button" className="cta" onClick={onClose}>
            {closeLabel}
          </button>
          {onUndo ? (
            <button type="button" className="sheet-undo" onClick={onUndo}>
              やっぱり見直す
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function hhmm(iso: string) {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}`;
}
