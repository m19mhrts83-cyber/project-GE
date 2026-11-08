"use client";

import type { WeekTally } from "@/lib/decisionContract";

/** 判断ログの粒。採った／見送った／迷った／未判断を色で分け、判断するたびに1粒落ちる */
export type Bead = "take" | "ng" | "hesitate" | "none" | "later" | "note";

const LABEL: Record<Bead, string> = {
  take: "採った",
  ng: "見送った",
  hesitate: "迷った",
  none: "未判断",
  later: "後で",
  note: "ひとこと",
};

const MAX = 48;

export default function LogJar({ week, session }: { week: WeekTally | null; session: Bead[] }) {
  const base: Bead[] = [];
  if (week) {
    for (const k of ["take", "ng", "hesitate", "none", "later", "note"] as Bead[]) {
      for (let i = 0; i < week[k]; i++) base.push(k);
    }
  }
  const all = [...base, ...session];
  const shown = all.slice(-MAX);
  const firstNew = shown.length - Math.min(session.length, shown.length);
  const counts = all.reduce<Record<string, number>>((a, b) => ((a[b] = (a[b] || 0) + 1), a), {});
  return (
    <div className="jar" aria-label={`今週の判断ログ ${all.length} 件`}>
      <div className="jar-glass">
        {shown.map((b, i) => (
          <span key={i} className={`bead ${b}${i >= firstNew ? " new" : ""}`} title={LABEL[b]} />
        ))}
      </div>
      <div className="jar-legend">
        <b className="mono">{all.length}</b>
        <span>今週のログ</span>
        {(["take", "ng", "hesitate"] as Bead[]).map((k) =>
          counts[k] ? (
            <span key={k} className="jar-k">
              <i className={`bead ${k}`} />
              {counts[k]}
            </span>
          ) : null,
        )}
      </div>
    </div>
  );
}
