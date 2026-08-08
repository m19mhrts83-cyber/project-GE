"use client";

import { useMemo, useState } from "react";
import {
  addDaysYmd,
  formatHealthBitsForDay,
  inferJournalSleepTags,
  preferVitalByDay,
  SLEEP_TAG_LABELS,
  ymdJst,
  type JournalDailyRow,
  type SnoreLite,
  type VitalLite,
} from "@/lib/quietEdgeContext";

export default function QuietEdgeJournalBand({
  journals,
  snore = [],
  vitals = [],
  windowDays = 14,
}: {
  journals: JournalDailyRow[];
  snore?: SnoreLite[];
  vitals?: VitalLite[];
  windowDays?: number;
}) {
  const [open, setOpen] = useState<string | null>(null);

  const snoreByDay = useMemo(() => {
    const m = new Map<string, SnoreLite>();
    for (const s of snore) m.set(s.recorded_at, s);
    return m;
  }, [snore]);

  const healthByDay = useMemo(() => preferVitalByDay(vitals), [vitals]);

  const recent = useMemo(() => {
    const today = ymdJst();
    const start = addDaysYmd(today, -(windowDays - 1));
    // Journal が無い日でも snore/Health がある日は行を出す（重ね表示）
    const days = new Set<string>();
    for (const j of journals) {
      if (j.recorded_at >= start && j.recorded_at <= today) days.add(j.recorded_at);
    }
    for (const s of snore) {
      if (s.recorded_at >= start && s.recorded_at <= today) days.add(s.recorded_at);
    }
    for (const v of vitals) {
      if (v.recorded_at >= start && v.recorded_at <= today) days.add(v.recorded_at);
    }
    return [...days].sort((a, b) => b.localeCompare(a));
  }, [journals, snore, vitals, windowDays]);

  const journalByDay = useMemo(() => {
    const m = new Map<string, JournalDailyRow>();
    for (const j of journals) m.set(j.recorded_at, j);
    return m;
  }, [journals]);

  const journalDays = recent.filter((d) => {
    const j = journalByDay.get(d);
    return j && j.excerpt.trim().length > 0;
  }).length;
  const withSignal = recent.filter((d) => {
    const j = journalByDay.get(d);
    if (!j) return false;
    return (
      (j.sleep_signal && j.sleep_signal.trim()) ||
      j.excerpt.includes("夜の防衛線")
    );
  }).length;

  return (
    <section className="card qe-journal-band">
      <header>
        <span className="lvl">Journal</span>
        <strong>日付ジョイン（★Journal × いびき × Health）</strong>
      </header>
      <p className="meta">
        全文ではなく「夜の防衛線」など睡眠関連を優先表示。直近 {windowDays} 日中
        Journal {journalDays} 日／睡眠シグナル {withSignal} 日。Mac で{" "}
        <code>jarvis_quiet_edge_journal_sync.py</code>（launchd 08:15）が更新。
      </p>
      {!recent.length ? (
        <p className="sum">まだ同期された Journal / バイタルがありません。</p>
      ) : (
        <ul className="qe-journal-list">
          {recent.map((day) => {
            const j = journalByDay.get(day);
            const thin = !j || !j.excerpt.trim() || j.char_count < 40;
            const isOpen = open === day;
            const tags = j
              ? j.sleep_tags && j.sleep_tags.length
                ? j.sleep_tags
                : inferJournalSleepTags(j.excerpt, j.sleep_signal)
              : [];
            const signal =
              (j?.sleep_signal && j.sleep_signal.trim()) ||
              j?.excerpt.split("\n").find((l) => l.includes("夜の防衛線")) ||
              "";
            const sn = snoreByDay.get(day);
            const healthBits = formatHealthBitsForDay(healthByDay.get(day));
            return (
              <li key={day} data-thin={thin ? "1" : "0"}>
                <button
                  type="button"
                  className="qe-journal-toggle"
                  onClick={() =>
                    setOpen((cur) => (cur === day ? null : day))
                  }
                >
                  <span className="qe-journal-main">
                    <strong>{day}</strong>
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
                    {healthBits ? (
                      <span className="meta"> · {healthBits}</span>
                    ) : (
                      <span className="meta"> · Healthなし</span>
                    )}
                  </span>
                  <span className="meta">{isOpen ? "閉じる" : "詳細"}</span>
                </button>
                {signal ? (
                  <p className="qe-sleep-signal">{signal}</p>
                ) : (
                  <p className="meta">
                    {j
                      ? "睡眠シグナル未検出（業務メモ中心の日）"
                      : "Journal 未同期／なし"}
                  </p>
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
                    {j?.excerpt.trim() || "（Journal 本文なし）"}
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
