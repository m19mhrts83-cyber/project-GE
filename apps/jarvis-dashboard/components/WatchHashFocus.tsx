"use client";

import { useEffect } from "react";

/**
 * ホーム「要フォロー」→ /situation?watch=<id>#watch-<id> の着地。
 * Next.js はハッシュ着地が弱いので、要素出現まで再試行してスクロール＋ハイライトする。
 */
function targetWatchDomId(): string | null {
  if (typeof window === "undefined") return null;
  const q = new URLSearchParams(window.location.search).get("watch");
  if (q) {
    const raw = decodeURIComponent(q.trim());
    return raw.startsWith("watch-") ? raw : `watch-${raw}`;
  }
  const hash = decodeURIComponent(window.location.hash.replace(/^#/, "").trim());
  if (!hash) return null;
  return hash.startsWith("watch-") ? hash : `watch-${hash}`;
}

function findWatchEl(domId: string): HTMLElement | null {
  const byPrefixed = document.getElementById(domId);
  if (byPrefixed) return byPrefixed;
  // 旧本番: id={it.id} のみだった時期の互換
  const bare = domId.replace(/^watch-/, "");
  if (bare && bare !== domId) {
    const byBare = document.getElementById(bare);
    if (byBare) return byBare;
    try {
      return document.querySelector<HTMLElement>(
        `[data-watch-id="${CSS.escape(bare)}"]`,
      );
    } catch {
      return document.querySelector<HTMLElement>(`[data-watch-id="${bare}"]`);
    }
  }
  return null;
}

export default function WatchHashFocus() {
  useEffect(() => {
    let cancelled = false;
    let highlightTimer: number | undefined;
    let retryTimer: number | undefined;
    let tries = 0;

    const clearHighlightSoon = (el: HTMLElement) => {
      el.classList.add("is-watch-focus");
      if (highlightTimer !== undefined) window.clearTimeout(highlightTimer);
      highlightTimer = window.setTimeout(() => {
        el.classList.remove("is-watch-focus");
        highlightTimer = undefined;
      }, 4500);
    };

    const apply = () => {
      if (cancelled) return;
      const domId = targetWatchDomId();
      if (!domId) return;
      const el = findWatchEl(domId);
      if (!el) {
        // SSR→hydrate・画像等でレイアウト確定まで待つ（最大 ~2s）
        if (tries++ < 40) {
          retryTimer = window.setTimeout(apply, 50);
        }
        return;
      }
      tries = 0;
      // レイアウト確定後にスクロール（1フレーム遅延）
      window.requestAnimationFrame(() => {
        if (cancelled) return;
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        clearHighlightSoon(el);
      });
    };

    const restart = () => {
      tries = 0;
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      apply();
    };

    restart();
    window.addEventListener("hashchange", restart);
    window.addEventListener("popstate", restart);
    return () => {
      cancelled = true;
      window.removeEventListener("hashchange", restart);
      window.removeEventListener("popstate", restart);
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      if (highlightTimer !== undefined) window.clearTimeout(highlightTimer);
    };
  }, []);

  return null;
}
