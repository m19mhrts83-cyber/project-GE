"use client";

import { useCallback, useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { setTriageStatus } from "@/app/actions/triage";
import { useToast } from "@/components/Toast";
import {
  formatSnoozeUntil,
  type SnoozePreset,
  snoozeUntilIso,
  SNOOZE_PRESET_LABEL,
} from "@/lib/snoozePresets";
import { LEVEL_LABEL, type HomeLevel } from "@/lib/homeLevels";

export type QueueRow = {
  key: string;
  kind: "mail" | "watch";
  id: string;
  href: string;
  external?: boolean;
  level: HomeLevel;
  title: string;
  detail: string;
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

type Props = { initialItems: QueueRow[] };

export default function QueueClient({ initialItems }: Props) {
  const router = useRouter();
  const toast = useToast();
  const [items, setItems] = useState(initialItems);
  const [idx, setIdx] = useState(0);
  const [pending, start] = useTransition();
  const [snoozePick, setSnoozePick] = useState(false);

  useEffect(() => {
    setItems(initialItems);
    setIdx(0);
  }, [initialItems]);

  const current = items[idx] || null;
  const remaining = items.length;

  const removeAt = useCallback((i: number) => {
    setItems((prev) => {
      const next = prev.slice(0, i).concat(prev.slice(i + 1));
      setIdx((cur) => {
        if (next.length === 0) return 0;
        return Math.min(cur, next.length - 1);
      });
      return next;
    });
  }, []);

  const applyMail = useCallback(
    (next: "skipped" | "snoozed", label: string, snoozeUntil?: string) => {
      if (!current || current.kind !== "mail" || pending) return;
      const row = current;
      const at = idx;
      start(async () => {
        const r = await setTriageStatus(
          row.id,
          next,
          "/queue",
          snoozeUntil ? { snoozeUntil } : undefined,
        );
        if (!r.ok) {
          toast.push(r.error, "err");
          return;
        }
        removeAt(at);
        toast.push(label, {
          undo: async () => {
            await setTriageStatus(row.id, r.prevStatus || "pending", "/queue");
            router.refresh();
          },
        });
        router.refresh();
      });
    },
    [current, pending, idx, removeAt, toast, router],
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
        if (map[key] && current?.kind === "mail") {
          e.preventDefault();
          const preset = map[key];
          setSnoozePick(false);
          applyMail(
            "snoozed",
            `後で（${SNOOZE_PRESET_LABEL[preset]}）`,
            snoozeUntilIso(preset),
          );
          return;
        }
        if ((key === "0" || key === "s") && current?.kind === "mail") {
          e.preventDefault();
          setSnoozePick(false);
          applyMail("snoozed", "後でにしました");
          return;
        }
        return;
      }

      if (key === "j" || key === "ArrowDown") {
        e.preventDefault();
        setIdx((i) => Math.min(i + 1, Math.max(items.length - 1, 0)));
        return;
      }
      if (key === "k" || key === "ArrowUp") {
        e.preventDefault();
        setIdx((i) => Math.max(i - 1, 0));
        return;
      }
      if (!current) return;
      if (key === "e" && current.kind === "mail") {
        e.preventDefault();
        applyMail("skipped", "スキップしました");
        return;
      }
      if (key === "s" && current.kind === "mail") {
        e.preventDefault();
        applyMail("snoozed", "後でにしました");
        return;
      }
      if (key === "h" && current.kind === "mail") {
        e.preventDefault();
        setSnoozePick(true);
        toast.push(
          "スヌーズ: 1=今日18時 2=明日9時 3=3日後 0=期限なし",
          "info",
        );
        return;
      }
      if (key === "Enter") {
        e.preventDefault();
        if (current.external) {
          window.open(current.href, "_blank", "noopener,noreferrer");
        } else {
          router.push(current.href);
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [items.length, current, snoozePick, applyMail, toast, router]);

  const hint = useMemo(() => {
    if (!current) return null;
    if (current.kind === "mail") {
      return (
        <>
          <kbd>e</kbd> スキップ · <kbd>s</kbd>/<kbd>h</kbd> 後で ·{" "}
          <kbd>Enter</kbd> 詳細・下書き · <kbd>z</kbd> 戻す
        </>
      );
    }
    return (
      <>
        <kbd>Enter</kbd> ウォッチを開く · <kbd>j</kbd>/<kbd>k</kbd> 前後
      </>
    );
  }, [current]);

  if (remaining === 0) {
    return (
      <section className="queue-done" aria-live="polite">
        <h2>キューは空です</h2>
        <p className="sub">いま手を動かす案件はありません。お疲れさまです。</p>
        <p>
          <a href="/" className="home-more">
            ホームへ →
          </a>
        </p>
      </section>
    );
  }

  return (
    <section className="queue-panel" aria-label="処理キュー">
      <div className="queue-head">
        <p className="queue-remain">
          残り <strong>{remaining}</strong> 件
          {pending ? " …" : ""}
        </p>
        <p className="kbd-hint" role="note">
          {hint}
          {snoozePick ? " · スヌーズ選択中" : ""}
        </p>
      </div>
      {current ? (
        <article className={`card focus-card level-${current.level}`}>
          <header>
            <span className="lvl">{LEVEL_LABEL[current.level]}</span>
            <span className="meta">
              {current.kind === "mail" ? "メール" : "ウォッチ"} · {idx + 1}/
              {remaining}
            </span>
          </header>
          <h2 style={{ fontSize: "1.2rem", margin: "8px 0" }}>
            {current.title}
          </h2>
          <p className="sum">{current.detail}</p>
          <div className="queue-actions">
            {current.kind === "mail" ? (
              <>
                <button
                  type="button"
                  className="btn"
                  disabled={pending}
                  onClick={() => applyMail("skipped", "スキップしました")}
                >
                  スキップ
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={pending}
                  onClick={() => applyMail("snoozed", "後でにしました")}
                >
                  後で
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={pending}
                  onClick={() => {
                    const until = snoozeUntilIso("tomorrow_am");
                    applyMail(
                      "snoozed",
                      `後で（${formatSnoozeUntil(until)}）`,
                      until,
                    );
                  }}
                >
                  明日 9:00
                </button>
              </>
            ) : null}
            <a
              className="btn primary"
              href={current.href}
              {...(current.external
                ? { target: "_blank", rel: "noopener noreferrer" }
                : {})}
            >
              {current.kind === "mail" ? "詳細・下書き →" : "開く →"}
            </a>
          </div>
        </article>
      ) : null}
      <ul className="queue-list-mini">
        {items.map((it, i) => (
          <li key={it.key}>
            <button
              type="button"
              className={`queue-mini-item${i === idx ? " is-active" : ""}`}
              onClick={() => setIdx(i)}
            >
              <span className="lvl">{LEVEL_LABEL[it.level]}</span>
              <span>{it.title}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
