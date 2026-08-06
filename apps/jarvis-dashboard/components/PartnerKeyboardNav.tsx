"use client";

import { useCallback, useEffect, useTransition } from "react";
import { useRouter } from "next/navigation";
import { setTriageStatus } from "@/app/actions/triage";
import { useToast } from "@/components/Toast";

type Props = {
  /** 現在のフォーカス index（0-based） */
  idx: number;
  total: number;
  focusId: string | null;
  path: string;
  prevHref: string | null;
  nextHref: string | null;
};

function isTypingTarget(t: EventTarget | null): boolean {
  if (!(t instanceof HTMLElement)) return false;
  const tag = t.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    t.isContentEditable
  );
}

/**
 * パートナー未読のキーボード・トリアージ。
 * j/k または ↑↓: 前後、e: スキップ、s: 後で、Enter: 詳細、?: ヘルプ（⌘K）
 */
export default function PartnerKeyboardNav({
  idx,
  total,
  focusId,
  path,
  prevHref,
  nextHref,
}: Props) {
  const router = useRouter();
  const toast = useToast();
  const [pending, start] = useTransition();

  const skipOrSnooze = useCallback(
    (next: "skipped" | "snoozed") => {
      if (!focusId || pending) return;
      start(async () => {
        const r = await setTriageStatus(focusId, next, path);
        if (!r.ok) {
          toast.push(r.error, "err");
          return;
        }
        toast.push(next === "skipped" ? "スキップしました" : "後でにしました");
        // リストが縮むので同じ idx の次件（末尾なら前へ）
        if (total <= 1) {
          router.push(path);
        } else if (idx < total - 1) {
          router.push(nextHref || path);
        } else if (prevHref) {
          router.push(prevHref);
        } else {
          router.push(path);
        }
        router.refresh();
      });
    },
    [focusId, pending, path, idx, total, nextHref, prevHref, router, toast],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isTypingTarget(e.target)) return;
      if (total === 0 && e.key !== "?") return;

      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;

      if (key === "j" || key === "ArrowDown") {
        if (nextHref) {
          e.preventDefault();
          router.push(nextHref);
        }
        return;
      }
      if (key === "k" || key === "ArrowUp") {
        if (prevHref) {
          e.preventDefault();
          router.push(prevHref);
        }
        return;
      }
      if (key === "e") {
        e.preventDefault();
        skipOrSnooze("skipped");
        return;
      }
      if (key === "s") {
        e.preventDefault();
        skipOrSnooze("snoozed");
        return;
      }
      if (key === "Enter" && focusId) {
        // フォーカスがリンク等でないときだけ詳細へ
        const t = e.target as HTMLElement | null;
        if (t?.tagName === "A" || t?.tagName === "BUTTON") return;
        e.preventDefault();
        router.push(`/mail/${encodeURIComponent(focusId)}`);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [total, nextHref, prevHref, focusId, router, skipOrSnooze]);

  if (total === 0) return null;

  return (
    <p className="kbd-hint" role="note">
      キーボード: <kbd>j</kbd>/<kbd>k</kbd> 前後 · <kbd>e</kbd> スキップ ·{" "}
      <kbd>s</kbd> 後で · <kbd>Enter</kbd> 詳細 · <kbd>⌘K</kbd> 移動
      {pending ? " …" : ""}
    </p>
  );
}
