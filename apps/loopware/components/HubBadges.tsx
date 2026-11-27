"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { propTopicId } from "@/lib/proposals";
import { jstDay, loadStore } from "@/lib/storage";

/** ハブのバッジのキー。/api/hub の項目と同じ */
export type HubKey =
  | "all"
  | "desk"
  | "left"
  | "misses"
  | "drafts"
  | "rules"
  | "zaim"
  | "week"
  | "inlet"
  | "outlet"
  | "slides"
  | "uiux";

type Counts = Partial<Record<HubKey, number | null>> & { deskCapped?: boolean };
type State = { ready: boolean; c: Counts };

const Ctx = createContext<State>({ ready: false, c: {} });

/** 合計に入れる項目（まとめて判断は他の合計、残り・次の一手は判断デスクの内数なので入れない） */
const SUMMARY: { k: HubKey; label: string }[] = [
  { k: "desk", label: "判断デスク" },
  { k: "misses", label: "見落とし" },
  { k: "drafts", label: "下書き" },
  { k: "rules", label: "今週の学び" },
  { k: "zaim", label: "Zaim" },
  { k: "week", label: "今週の9件" },
  { k: "inlet", label: "312 入口" },
  { k: "outlet", label: "313 出口" },
  { k: "slides", label: "資料づくり" },
  { k: "uiux", label: "画面の好み" },
];

export function HubCountsProvider({ children }: { children: ReactNode }) {
  const [s, setS] = useState<State>({ ready: false, c: {} });
  useEffect(() => {
    fetch("/api/hub", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => {
        if (!j?.ok) return setS({ ready: true, c: {} });
        // 312 の提案は、この端末で今日仕分けた分を引いてから入口に足す
        const done = new Set(loadStore().decisions.map((d) => d.topicId));
        const day = jstDay();
        const props = Array.isArray(j.proposalIds)
          ? (j.proposalIds as string[]).filter((id) => !done.has(propTopicId(day, id))).length
          : null;
        const inlet = j.inlet === null && props === null ? null : (j.inlet ?? 0) + (props ?? 0);
        setS({ ready: true, c: { ...j, inlet } });
      })
      .catch(() => setS({ ready: true, c: {} }));
  }, []);
  return <Ctx.Provider value={s}>{children}</Ctx.Provider>;
}

/** 項目の右端のバッジ。残りがあれば赤い数字、0件は✓、読めないときは出さない */
export function HubBadge({ k }: { k: HubKey }) {
  const { ready, c } = useContext(Ctx);
  if (!ready) return <span className="hub-badge wait" aria-hidden="true" />;
  const n = c[k];
  if (n === null || n === undefined) return null;
  if (n <= 0) return <span className="hub-badge zero" aria-label="対応なし">✓</span>;
  const capped = k === "desk" && c.deskCapped;
  return (
    <span className="hub-badge" aria-label={`残り${n}件`}>
      {n}
      {capped ? "+" : ""}
    </span>
  );
}

/** ハブ上部の「全体で何が残っているか」 */
export function HubSummary() {
  const { ready, c } = useContext(Ctx);
  if (!ready) return null;
  const known = SUMMARY.filter((x) => typeof c[x.k] === "number");
  if (!known.length) return null;
  const open = known.filter((x) => (c[x.k] as number) > 0);
  const total = open.reduce((a, x) => a + (c[x.k] as number), 0);
  const unknown = SUMMARY.length - known.length;
  return (
    <div className={`glass hub-summary ${open.length ? "" : "clear"}`}>
      {open.length ? (
        <>
          <div className="hub-summary-head">
            <b className="mono">{total}</b>
            <span>
              件が対応待ち（{open.length}項目）
            </span>
          </div>
          <div className="hub-summary-list">
            {open.map((x) => (
              <span key={x.k} className="hub-chip">
                {x.label} <b>{c[x.k]}</b>
              </span>
            ))}
          </div>
        </>
      ) : (
        <div className="hub-summary-head">
          <span>✓ いま対応待ちはありません</span>
        </div>
      )}
      {unknown ? <p className="meta" style={{ margin: "6px 0 0" }}>読めなかった項目 {unknown}件（バッジなし）</p> : null}
    </div>
  );
}
