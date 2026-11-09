"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Icon from "./Icon";
import { SEED_PROPOSALS, propTopicId } from "@/lib/proposals";
import { jstDay, loadDaily, loadStore } from "@/lib/storage";

/** 毎日の仕分け：今日の分が終われば「完了」。ログは溜まり、週1のレビューで基準へ。 */
export default function FocusCard() {
  const [total, setTotal] = useState(SEED_PROPOSALS.length);
  const [ids, setIds] = useState<string[]>(SEED_PROPOSALS.map((p) => p.id));
  const [doneIds, setDoneIds] = useState<string[]>([]);
  const [daysDone, setDaysDone] = useState(0);
  const [logs, setLogs] = useState(0);
  const [ready, setReady] = useState(false);
  const day = jstDay();

  useEffect(() => {
    const dec = loadStore().decisions;
    setDoneIds(dec.map((d) => d.topicId));
    setLogs(dec.length);
    setDaysDone(Object.keys(loadDaily()).length);
    fetch("/api/misses")
      .then((r) => r.json())
      .then((j) => {
        if (Array.isArray(j?.candidates) && j.candidates.length) {
          setIds(j.candidates.map((c: { id: string }) => c.id));
          setTotal(j.candidates.length);
        }
      })
      .catch(() => undefined)
      .finally(() => setReady(true));
  }, []);

  if (!ready) {
    return (
      <div className="glass" style={{ padding: 20, minHeight: 190 }}>
        <span className="meta">今日の仕分けを確認しています…</span>
      </div>
    );
  }

  const pending = ids.filter((id) => !doneIds.includes(propTopicId(day, id)));

  if (!pending.length) {
    return (
      <div className="glass" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 10 }}>
        <div className="eyebrow acc" style={{ color: "var(--positive)", display: "flex", gap: 8, alignItems: "center" }}>
          <Icon name="check" size={16} stroke={3} /> TODAY DONE
        </div>
        <p style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>今日の仕分けは完了</p>
        <p className="meta" style={{ margin: 0 }}>
          {total}件を仕分けました。判断ログ {logs}件が溜まっています。週1のレビューで基準へ。
        </p>
        <Link className="secondary" href="/review" style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
          週1のレビューを開く <Icon name="arrow" size={16} />
        </Link>
      </div>
    );
  }

  return (
    <div className="focus-card">
      <div className="label">
        <Icon name="clock" size={18} />
        <span className="eyebrow" style={{ margin: 0, color: "inherit" }}>今日の仕分け</span>
      </div>
      <div className="big">
        <b>{pending.length}</b>
        <span>件が未仕分け</span>
      </div>
      <div>採る・見送る・保留で仕分けて保存すると、今日は完了。{daysDone ? `これまで ${daysDone}日分が完了。` : ""}</div>
      <Link className="cta" href="/312?tab=misses" style={{ textDecoration: "none" }}>
        仕分ける <Icon name="arrow" size={18} stroke={2.4} />
      </Link>
    </div>
  );
}
