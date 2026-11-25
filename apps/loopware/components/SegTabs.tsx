"use client";

import Link from "next/link";
import { useCounts, type Counts } from "./useCounts";

export type SegTab = { href: string; label: string; key: "topics" | "misses" | "cleanup" | "closeLeak" | null; active: boolean };

/** タブ。残り件数をバッジで出す（0件は✓、読めないときは出さない） */
export default function SegTabs({ tabs }: { tabs: SegTab[] }) {
  const counts = useCounts();
  return (
    <div className="seg segn" style={{ gridTemplateColumns: `repeat(${tabs.length}, 1fr)`, marginBottom: 14 }}>
      {tabs.map((t) => (
        <Link key={t.href} className={t.active ? "active" : ""} href={t.href}>
          <span className="seg-label">{t.label}</span>
          <Badge counts={counts} k={t.key} />
        </Link>
      ))}
    </div>
  );
}

function Badge({ counts, k }: { counts: Counts; k: SegTab["key"] }) {
  if (!k) return null;
  const n = counts[k];
  if (n === null || n === undefined) return null;
  return n > 0 ? (
    <span className="seg-badge" aria-label={`残り${n}件`}>{n}</span>
  ) : (
    <span className="seg-badge zero" aria-label="残りなし">✓</span>
  );
}
