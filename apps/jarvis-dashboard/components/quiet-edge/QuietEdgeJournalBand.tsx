"use client";

import { useMemo, useState } from "react";
import {
  addDaysYmd,
  inferJournalSleepTags,
  SLEEP_TAG_LABELS,
  ymdJst,
  type JournalDailyRow,
  type SnoreLite,
} from "@/lib/quietEdgeContext";

export default function QuietEdgeJournalBand({
  journals,
  snore = [],
  windowDays = 14,
}: {
  journals: JournalDailyRow[];
  snore?: SnoreLite[];
  windowDays?: number;
}) {
  const [open, setOpen] = useState<string | null>(null);

  const snoreByDay = useMemo(() => {
    const m = new Map<string, SnoreLite>();
    for (const s of snore) m.set(s.recorded_at, s);
    return m;
  }, [snore]);

  const recent = useMemo(() => {
    const today = ymdJst();
    const start = addDaysYmd(today, -(windowDays - 1));
    return [...journals]
      .filter((j) => j.recorded_at >= start && j.recorded_at <= today)
      .sort((a, b) => b.recorded_at.localeCompare(a.recorded_at));
  }, [journals, windowDays]);

  const withText = recent.filter((j) => j.excerpt.trim().length > 0);
  const coverage = recent.length;
  const withSignal = recent.filter(
    (j) => (j.sleep_signal && j.sleep_signal.trim()) || j.excerpt.includes("夜の防衛線"),
  ).length;

  return (
    <section className="card qe-journal-band">
      <header>
        <span className="lvl">Journal</span>
        <strong>睡眠シグナル（★Journal）</strong>
      </header>
      <p className="meta">
        全文ではなく「夜の防衛線」など睡眠関連を優先表示します。直近 {windowDays}{" "}
        日中 Journal {coverage} 日／睡眠シグナル {withSignal} 日。
        Mac で <code>jarvis_quiet_edge_journal_sync.py</code> を実行して更新。
      </p>
      {!withText.length ? (
        <p className="sum">まだ同期された Journal がありません。</p>
      ) : (
        <ul className="qe-journal-list">
          {recent.map((j) => {
            const thin = !j.excerpt.trim() || j.char_count < 40;
            const isOpen = open === j.recorded_at;
            const tags =
              j.sleep_tags && j.sleep_tags.length
                ? j.sleep_tags
                : inferJournalSleepTags(j.excerpt, j.sleep_signal);
            const signal =
              (j.sleep_signal && j.sleep_signal.trim()) ||
              j.excerpt.split("\n").find((l) => l.includes("夜の防衛線")) ||
              "";
            const sn = snoreByDay.get(j.recorded_at);
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
                  <span className="qe-journal-main">
                    <strong>{j.recorded_at}</strong>
                    {sn ? (
                      <span className="meta">
                        {" "}
                        · いびき {Number(sn.score).toFixed(1)}
                        {sn.count != null
                          ? ` / ${sn.count.toLocaleString("ja-JP")}回`
                          : ""}
                      </span>
                    ) : (
                      <span className="meta"> · いびき記録なし</span>
                    )}
                  </span>
                  <span className="meta">{isOpen ? "閉じる" : "詳細"}</span>
                </button>
                {signal ? (
                  <p className="qe-sleep-signal">{signal}</p>
                ) : (
                  <p className="meta">睡眠シグナル未検出（業務メモ中心の日）</p>
                )}
                {tags.length ? (
                  <div className="qe-sleep-tags">
                    {tags.map((t) => (
                      <span key={t} data-tag={t}>
                        {SLEEP_TAG_LABELS[t] || t}
                      </span>
                    ))}
                  </div>
                ) : null}
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
