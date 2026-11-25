"use client";

import { useEffect, useState } from "react";
import { propTopicId } from "@/lib/proposals";
import { jstDay, loadStore } from "@/lib/storage";

export type Counts = {
  ready: boolean;
  /** 312 扱いを決める */
  topics: number | null;
  /** 312 提案を仕分ける（この端末で仕分け済みの分は引く） */
  misses: number | null;
  /** 313 まとめて片付ける */
  cleanup: number | null;
  /** 313 閉じ漏れ（Mac の検知がまだ一度も届いていない・読めない間は null） */
  closeLeak: number | null;
};

/** タブのバッジ用。読めなかったものは null（0件とは別に扱う） */
export function useCounts(): Counts {
  const [c, setC] = useState<Counts>({ ready: false, topics: null, misses: null, cleanup: null, closeLeak: null });
  useEffect(() => {
    fetch("/api/counts", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (!j?.ok) return setC((p) => ({ ...p, ready: true }));
        const done = new Set(loadStore().decisions.map((d) => d.topicId));
        const day = jstDay();
        const misses = Array.isArray(j.missIds) ? j.missIds.filter((id: string) => !done.has(propTopicId(day, id))).length : null;
        setC({ ready: true, topics: j.topics, misses, cleanup: j.cleanup, closeLeak: j.closeLeak });
      })
      .catch(() => setC((p) => ({ ...p, ready: true })));
  }, []);
  return c;
}
