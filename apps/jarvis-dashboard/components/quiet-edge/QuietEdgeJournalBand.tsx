"use client";

import { useMemo, useState } from "react";
import {
  addDaysYmd,
  ymdJst,
  type JournalDailyRow,
} from "@/lib/quietEdgeContext";

export default function QuietEdgeJournalBand({
  journals,
  windowDays = 14,
}: {
  journals: JournalDailyRow[];
  windowDays?: number;
}) {
  const [open, setOpen] = useState<string | null>(null);

  const recent = useMemo(() => {
    const today = ymdJst();
    const start = addDaysYmd(today, -(windowDays - 1));
    return [...journals]
      .filter((j) => j.recorded_at >= start && j.recorded_at <= today)
      .sort((a, b) => b.recorded_at.localeCompare(a.recorded_at));
  }, [journals, windowDays]);

  const withText = recent.filter((j) => j.excerpt.trim().length > 0);
  const coverage = recent.length;

  return (
    <section className="card qe-journal-band">
      <header>
        <span className="lvl">Journal</span>
        <strong>★Journal（日付ジョイン）</strong>
      </header>
      <p className="meta">
        Obsidian の日次メモ抜粋。Mac で
        <code> jarvis_quiet_edge_journal_sync.py </code>
        を走らせるとここに載ります（直近 {windowDays} 日中 {coverage} 日分）。
      </p>
      {!withText.length ? (
        <p className="sum">まだ同期された Journal がありません。</p>
      ) : (
        <ul className="qe-journal-list">
          {recent.map((j) => {
            const thin = !j.excerpt.trim() || j.char_count < 40;
            const isOpen = open === j.recorded_at;
            return (
              <li key={j.recorded_at} data-thin={thin ? "1" : "0"}>
                <button
                  type="button"
                  className="qe-journal-toggle"
                  onClick={() =>
                    setOpen((cur) =>
                      cur === j.recorded_at ? null : j.recorded_at,
                    )
                  }
                >
                  <strong>{j.recorded_at}</strong>
                  <span className="meta">
                    {thin ? "薄い／なし" : `${j.char_count}字`}
                    {isOpen ? " · 閉じる" : " · 抜粋"}
                  </span>
                </button>
                {isOpen ? (
                  <pre className="qe-journal-excerpt">
                    {j.excerpt.trim() || "（本文なし）"}
                  </pre>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
