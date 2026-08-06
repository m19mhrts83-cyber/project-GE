"use client";

import { useCallback, useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { setTriageStatus } from "@/app/actions/triage";
import { useToast } from "@/components/Toast";
import {
  type SnoozePreset,
  snoozeUntilIso,
  SNOOZE_PRESET_LABEL,
} from "@/lib/snoozePresets";

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
 * j/k: 前後、e: スキップ、s: 即スヌーズ、h: 時間付きスヌーズ、z: Undo、Enter: 詳細
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
  const [snoozePick, setSnoozePick] = useState(false);

  const afterMove = useCallback(() => {
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
  }, [total, idx, nextHref, prevHref, path, router]);

  const applyStatus = useCallback(
    (next: "skipped" | "snoozed", label: string, snoozeUntil?: string) => {
      if (!focusId || pending) return;
      start(async () => {
        const r = await setTriageStatus(
          focusId,
          next,
          path,
          snoozeUntil ? { snoozeUntil } : undefined,
        );
        if (!r.ok) {
          toast.push(r.error, "err");
          return;
        }
        const id = focusId;
        const prev = r.prevStatus || "pending";
        toast.push(label, {
          undo: async () => {
            await setTriageStatus(id, prev, path);
            router.refresh();
          },
        });
        afterMove();
      });
    },
    [focusId, pending, path, toast, afterMove, router],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isTypingTarget(e.target)) return;

      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;

      if (snoozePick) {
        if (key === "Escape") {
          e.preventDefault();
          setSnoozePick(false);
          return;
        }
        const map: Record<string, SnoozePreset> = {
          "1": "evening",
          "2": "tomorrow_am",
          "3": "plus_3d",
        };
        if (map[key]) {
          e.preventDefault();
          const preset = map[key];
          const until = snoozeUntilIso(preset);
          setSnoozePick(false);
          applyStatus(
            "snoozed",
            `後で（${SNOOZE_PRESET_LABEL[preset]}）`,
            until,
          );
          return;
        }
        if (key === "0" || key === "s") {
          e.preventDefault();
          setSnoozePick(false);
          applyStatus("snoozed", "後でにしました");
          return;
        }
        return;
      }

      if (total === 0) return;

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
        applyStatus("skipped", "スキップしました");
        return;
      }
      if (key === "s") {
        e.preventDefault();
        applyStatus("snoozed", "後でにしました");
        return;
      }
      if (key === "h") {
        e.preventDefault();
        setSnoozePick(true);
        toast.push("スヌーズ: 1=今日18時 2=明日9時 3=3日後 0=期限なし（Escで取消）", "info");
        return;
      }
      if (key === "Enter" && focusId) {
        const t = e.target as HTMLElement | null;
        if (t?.tagName === "A" || t?.tagName === "BUTTON") return;
        e.preventDefault();
        router.push(`/mail/${encodeURIComponent(focusId)}`);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    total,
    nextHref,
    prevHref,
    focusId,
    router,
    applyStatus,
    snoozePick,
    toast,
  ]);

  if (total === 0) return null;

  return (
    <p className="kbd-hint" role="note">
      キーボード: <kbd>j</kbd>/<kbd>k</kbd> 前後 · <kbd>e</kbd> スキップ ·{" "}
      <kbd>s</kbd> 後で · <kbd>h</kbd> 時間スヌーズ · <kbd>z</kbd> 戻す ·{" "}
      <kbd>Enter</kbd> 詳細 · <kbd>⌘K</kbd> コマンド
      {pending ? " …" : ""}
      {snoozePick ? " · スヌーズ選択中" : ""}
    </p>
  );
}
