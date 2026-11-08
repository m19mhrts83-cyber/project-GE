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
  // いけともさんの「モーション」資料と同じ作り方：章の経過時間 t から毎フレーム状態を決める。
// CSS の delay に任せないので、スキップ・動きを減らす設定でも完成形に飛べる。
  const STEP = 240;
  const BASE = 350;
  const linesEnd = BASE + lines.length * STEP;
  const T_COUNT = linesEnd + 150;
  const T_STACK = T_COUNT + 250;
  const T_END = T_STACK + 500;

  const [t, setT] = useState(0);
  const [done, setDone] = useState(false);
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
    const reduce =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setDone(true);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const el = now - start;
      setT(el);
      if (el >= T_END) setDone(true);
      else raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [T_END]);

  const at = (ms: number) => done || t >= ms;
  // 件数は ease-out（1-(1-x)^3）で増える。章の経過時間から計算
  const x = done ? 1 : Math.max(0, Math.min(1, (t - T_COUNT) / 500));
  const eased = 1 - Math.pow(1 - x, 3);
  const shown = Math.round(total - 1 + eased);

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
      <div className={`sheet ${done ? "done" : ""}`}>
        <div className="sheet-head">
          <span className="sheet-ring" aria-hidden="true">
            <Icon name="check" size={22} stroke={3} />
          </span>
          <div style={{ flexGrow: 1 }}>
            <div className="eyebrow acc" style={{ color: "var(--positive)" }}>
              SAVED
            </div>
            <div className="sheet-title">{decisionLabel}</div>
          </div>
          {!done ? (
            <button type="button" className="skip" onClick={() => setDone(true)}>
              スキップ
            </button>
          ) : null}
        </div>

        <ul className="log-lines" aria-label="保存したログ">
          {lines.map((l, i) => (
            <li key={l.k} className={`log-line ${at(BASE + i * STEP) ? "in" : ""}`}>
              <span className="log-k">{l.k}</span>
              <span className="log-v">{l.v}</span>
              <span className={`log-tick ${at(BASE + i * STEP + 160) ? "in" : ""}`}>
                <Icon name="check" size={12} stroke={3.5} />
              </span>
            </li>
          ))}
        </ul>

        <div className={`log-count ${at(T_COUNT - 100) ? "in" : ""}`}>
          <span className="meta">判断ログ</span>
          <span className="mono count-num">
            {shown}
            <small> 件</small>
          </span>
          <span className={`count-plus mono ${at(T_COUNT) ? "in" : ""}`}>+1</span>
        </div>

        <ol className="log-stack" aria-label="ログの積み上がり">
          <li className={`stack-new ${at(T_STACK) ? "in" : ""}`}>
            <span className="mono">{hhmm(rec.decidedAt)}</span>
            <span>
              {rec.agentId} · {decisionLabel}
            </span>
            <span className="stack-badge">NEW</span>
          </li>
          {past.map((r, i) => (
            <li
              key={`${r.topicId}-${r.decidedAt}`}
              className={`stack-old ${at(T_STACK + 100 + i * 90) ? "in" : ""}`}
            >
              <span className="mono">{hhmm(r.decidedAt)}</span>
              <span>
                {r.agentId} ·{" "}
                {r.finalText ? r.finalText.split("\n")[0].slice(0, 28) : r.topicId}
              </span>
            </li>
          ))}
        </ol>

        <div className={`ending ${done ? "in" : ""}`} aria-hidden={!done}>
          <div className="layers">
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

          <div className="ready">
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
        </div>

        <div className={`sheet-actions ${done ? "in" : ""}`}>
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
