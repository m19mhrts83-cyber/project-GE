"use client";

import { useEffect, useRef, useState } from "react";
import { PULSE_EVENT, crossedMilestone, type Pulse, type PulseBead } from "@/lib/logPulse";

/**
 * 判断ログに残ったときのモーション（全画面共通。layout に1つだけ置く）。
 * 1) 中央でチェックの輪が描かれ、粒が生まれる
 * 2) 粒が右上の瓶へ飛び込み、瓶の中身がせり上がり、件数がくるっと繰り上がる
 * 3) 10件ごと・区切りの判断では、紙吹雪で「たまった」を祝う
 * 件数は今週の判断ログ（/api/log）。数え直しは裏で行い、画面の手応えは先に出す。
 */

type Show = {
  id: number;
  pulse: Pulse;
  from: number;
  to: number;
  milestone: number;
};

const LABEL: Record<PulseBead, string> = {
  take: "採った",
  ng: "見送った",
  hesitate: "迷った",
  none: "未判断",
  later: "今回だけ",
  note: "ひとこと",
};

const STACK_MAX = 30; // 瓶が満杯に見える件数（それ以上は満杯のまま件数だけ増える）
const SHOW_MS = 2300;
const SHOW_BIG_MS = 3200;
const SHOW_COMPACT_MS = 1500;
const CONFETTI = 22;

async function fetchWeekTotal(): Promise<number | null> {
  try {
    const r = await fetch("/api/log", { cache: "no-store" });
    const j = await r.json();
    return j && j.ok && j.tally && typeof j.tally.total === "number" ? j.tally.total : null;
  } catch {
    return null;
  }
}

export default function LogCelebration() {
  const [show, setShow] = useState<Show | null>(null);
  const totalRef = useRef<number | null>(null);
  const seq = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    function onPulse(e: Event) {
      const pulse = (e as CustomEvent<Pulse>).detail;
      if (!pulse || !pulse.beads?.length) return;
      const n = pulse.beads.length;
      const id = ++seq.current;

      const play = (from: number, to: number) => {
        totalRef.current = to;
        const milestone = crossedMilestone(from, to);
        setShow({ id, pulse, from, to, milestone });
        if (timer.current) clearTimeout(timer.current);
        const ms = pulse.compact && !milestone ? SHOW_COMPACT_MS : pulse.big || milestone ? SHOW_BIG_MS : SHOW_MS;
        timer.current = setTimeout(() => setShow((s) => (s && s.id === id ? null : s)), ms);
      };

      const known = totalRef.current;
      if (known !== null) {
        play(known, known + n);
        // 裏で数え直し（別の端末・別の画面の判断も含める）
        void fetchWeekTotal().then((t) => {
          if (t !== null && totalRef.current !== null && t > totalRef.current) {
            totalRef.current = t;
          }
        });
      } else {
        // 初回だけ数を取りに行く（記録の後なので今回の分も入っている）
        void fetchWeekTotal().then((t) => {
          if (seq.current !== id && totalRef.current !== null) return; // 先に別の演出が始まった
          const to = t !== null ? Math.max(t, n) : n;
          play(to - n, to);
        });
      }
    }
    window.addEventListener(PULSE_EVENT, onPulse);
    return () => {
      window.removeEventListener(PULSE_EVENT, onPulse);
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);

  if (!show) return null;
  const { pulse, from, to, milestone } = show;
  const compact = Boolean(pulse.compact) && !milestone;
  const big = Boolean(pulse.big) || milestone > 0;
  const fillFrom = Math.min(from, STACK_MAX) / STACK_MAX;
  const fillTo = Math.min(to, STACK_MAX) / STACK_MAX;
  const added = to - from;
  const head = pulse.beads[pulse.beads.length - 1];
  const caption = pulse.label || LABEL[head];

  return (
    <div className={`lc${compact ? " lc-compact" : ""}${big ? " lc-big" : ""}`} key={show.id} role="status" aria-live="polite">
      <span className="sr-only">
        判断ログに記録しました。今週 {to} 件{milestone ? `。${milestone} 件たまりました` : ""}
      </span>

      {!compact ? (
        <div className="lc-center" aria-hidden="true">
          <svg className="lc-ring" viewBox="0 0 72 72" width="72" height="72">
            <circle className="lc-ring-bg" cx="36" cy="36" r="30" />
            <circle className="lc-ring-fg" cx="36" cy="36" r="30" />
            <path className="lc-check" d="M24 37 l8 8 l16 -18" />
          </svg>
          <div className="lc-caption">{caption}</div>
          <div className="lc-sub">判断ログに残しました</div>
          {pulse.beads.slice(0, 8).map((b, i) => (
            <span key={i} className={`lc-fly bead ${b}`} style={{ animationDelay: `${520 + i * 90}ms` }} />
          ))}
        </div>
      ) : null}

      <div className="lc-jar" aria-hidden="true">
        <div className="lc-jar-glass">
          <div
            className="lc-jar-fill"
            style={{ ["--fill-from" as string]: String(fillFrom), ["--fill-to" as string]: String(fillTo) } as React.CSSProperties}
          />
          <div className="lc-jar-shine" />
        </div>
        <div className="lc-jar-text">
          <span className="lc-plus mono">+{added}</span>
          <span className="lc-count mono">
            <span className="lc-odo">
              <span className="lc-odo-old">{from}</span>
              <span className="lc-odo-new">{to}</span>
            </span>
          </span>
          <span className="lc-unit">今週のログ</span>
        </div>
      </div>

      {big ? (
        <div className="lc-confetti" aria-hidden="true">
          {Array.from({ length: CONFETTI }).map((_, i) => {
            const angle = (i / CONFETTI) * Math.PI * 2;
            const dist = 90 + ((i * 37) % 70);
            return (
              <i
                key={i}
                className={`lc-bit c${i % 5}`}
                style={
                  {
                    ["--dx" as string]: `${Math.round(Math.cos(angle) * dist)}px`,
                    ["--dy" as string]: `${Math.round(Math.sin(angle) * dist - 40)}px`,
                    ["--rot" as string]: `${(i * 67) % 360}deg`,
                    animationDelay: `${(i % 4) * 30}ms`,
                  } as React.CSSProperties
                }
              />
            );
          })}
        </div>
      ) : null}

      {big ? <div className="lc-banner">{milestone ? `${milestone} 件たまりました` : "ひと区切り、記録しました"}</div> : null}
    </div>
  );
}
