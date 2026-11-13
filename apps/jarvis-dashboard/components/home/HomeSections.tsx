"use client";

import { useCallback, useRef, useState, type ReactNode } from "react";
import { HOME_ORDER_COOKIE, normalizeHomeOrder } from "@/lib/homeOrder";

/**
 * ホームのカードの並び替え。「並べ替え」を押すとカードが見出しだけの一覧になり、
 * つまみをドラッグ（スマホは長押し不要でそのまま指で）または ↑↓ で動かす。
 * 並びはこの端末の cookie に保存し、次からはサーバー側でその順に描く（ちらつかない）。
 */

export type HomeSection = { id: string; label: string; node: ReactNode };

function saveOrder(order: string[]) {
  document.cookie = `${HOME_ORDER_COOKIE}=${encodeURIComponent(order.join(","))}; path=/; max-age=${60 * 60 * 24 * 400}; samesite=lax`;
}

function withTransition(fn: () => void) {
  const d = document as Document & { startViewTransition?: (cb: () => void) => unknown };
  const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  if (d.startViewTransition && !reduce) d.startViewTransition(fn);
  else fn();
}

export default function HomeSections({ sections, initialOrder, defaultOrder }: { sections: HomeSection[]; initialOrder: string[]; defaultOrder: string[] }) {
  const ids = sections.map((s) => s.id);
  const [order, setOrder] = useState<string[]>(() => normalizeHomeOrder(initialOrder, ids));
  const [editing, setEditing] = useState(false);
  const [dragId, setDragId] = useState<string | null>(null);
  const listRef = useRef<HTMLOListElement>(null);
  const byId = Object.fromEntries(sections.map((s) => [s.id, s]));

  const commit = useCallback((next: string[]) => {
    setOrder(next);
    saveOrder(next);
  }, []);

  const move = (id: string, delta: number) => {
    const i = order.indexOf(id);
    const j = i + delta;
    if (i < 0 || j < 0 || j >= order.length) return;
    const next = [...order];
    [next[i], next[j]] = [next[j], next[i]];
    withTransition(() => commit(next));
  };

  const onPointerDown = (id: string) => (e: React.PointerEvent<HTMLButtonElement>) => {
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    setDragId(id);
  };

  const onPointerMove = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (!dragId || !listRef.current) return;
    const items = Array.from(listRef.current.querySelectorAll<HTMLLIElement>("li[data-id]"));
    const y = e.clientY;
    let target = items.length - 1;
    for (let k = 0; k < items.length; k++) {
      const r = items[k].getBoundingClientRect();
      if (y < r.top + r.height / 2) {
        target = k;
        break;
      }
    }
    const from = order.indexOf(dragId);
    if (target === from) return;
    const next = order.filter((x) => x !== dragId);
    next.splice(target, 0, dragId);
    setOrder(next);
  };

  const onPointerUp = () => {
    if (!dragId) return;
    setDragId(null);
    saveOrder(order);
  };

  return (
    <div className={`home-sections${editing ? " is-editing" : ""}`}>
      <div className="home-sections-bar">
        {editing ? (
          <>
            <span className="home-sections-hint">つまみ（⋮⋮）をドラッグするか、↑↓で動かします。この端末に保存されます。</span>
            <button type="button" className="btn ghost" onClick={() => withTransition(() => commit(normalizeHomeOrder(defaultOrder, ids)))}>
              最初の並びに戻す
            </button>
            <button type="button" className="btn primary" onClick={() => withTransition(() => setEditing(false))}>
              完了
            </button>
          </>
        ) : (
          <button type="button" className="btn ghost home-sections-edit" onClick={() => withTransition(() => setEditing(true))}>
            ⇅ カードを並べ替え
          </button>
        )}
      </div>

      {editing ? (
        <ol className="home-sort-list" ref={listRef} aria-label="ホームのカードの並び">
          {order.map((id, i) => (
            <li key={id} data-id={id} className={dragId === id ? "is-dragging" : ""} style={{ viewTransitionName: `hs-${id}` }}>
              <button
                type="button"
                className="home-sort-handle"
                aria-label={`${byId[id]?.label} をドラッグして移動`}
                onPointerDown={onPointerDown(id)}
                onPointerMove={onPointerMove}
                onPointerUp={onPointerUp}
                onPointerCancel={onPointerUp}
              >
                ⋮⋮
              </button>
              <span className="home-sort-num">{i + 1}</span>
              <span className="home-sort-label">{byId[id]?.label}</span>
              <button type="button" className="home-sort-arrow" aria-label="上へ" disabled={i === 0} onClick={() => move(id, -1)}>
                ↑
              </button>
              <button type="button" className="home-sort-arrow" aria-label="下へ" disabled={i === order.length - 1} onClick={() => move(id, 1)}>
                ↓
              </button>
            </li>
          ))}
        </ol>
      ) : (
        order.map((id) => (
          <div key={id} className="home-section" data-section={id} style={{ viewTransitionName: `hs-${id}` }}>
            {byId[id]?.node}
          </div>
        ))
      )}
    </div>
  );
}
