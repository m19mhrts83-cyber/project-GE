"use client";

import { useRouter } from "next/navigation";
import { useOptimistic, useTransition } from "react";
import { setTriageStatus } from "@/app/actions/triage";
import type { TriageStatus } from "@/lib/triageStatus";
import { STATUS_LABEL, isUnread } from "@/lib/triageStatus";
import { useToast } from "@/components/Toast";
import SnoozeMenu from "@/components/SnoozeMenu";
import { formatSnoozeUntil, type SnoozePreset } from "@/lib/snoozePresets";

type Props = {
  id: string;
  status: string;
  path: string;
  /** 未読カード用: スキップ／後で。処理済み用: 未読に戻す */
  mode?: "unread" | "closed";
  snoozeUntil?: string | null;
};

export default function TriageStatusActions({
  id,
  status,
  path,
  mode,
  snoozeUntil,
}: Props) {
  const router = useRouter();
  const toast = useToast();
  const [pending, start] = useTransition();
  const [optimisticStatus, setOptimistic] = useOptimistic(status);
  const unread = isUnread(optimisticStatus);
  const view = mode || (unread ? "unread" : "closed");

  function go(
    next: TriageStatus,
    label: string,
    opts?: { snoozeUntil?: string | null },
  ) {
    start(async () => {
      const prev = optimisticStatus as TriageStatus;
      setOptimistic(next);
      const r = await setTriageStatus(id, next, path, opts);
      if (!r.ok) {
        toast.push(r.error, "err");
        router.refresh();
        return;
      }
      toast.push(label, {
        undo: async () => {
          await setTriageStatus(id, r.prevStatus || prev, path);
          router.refresh();
        },
      });
      router.refresh();
    });
  }

  if (view === "closed") {
    return (
      <div className="triage-actions" style={{ marginLeft: "auto" }}>
        <span className={`status-badge status-${optimisticStatus}`}>
          {STATUS_LABEL[optimisticStatus as TriageStatus] || optimisticStatus}
        </span>
        {optimisticStatus === "snoozed" && snoozeUntil ? (
          <span className="meta" style={{ fontSize: "0.75rem" }}>
            → {formatSnoozeUntil(snoozeUntil)}
          </span>
        ) : null}
        <button
          type="button"
          className="btn"
          style={{ padding: "4px 10px", fontSize: "0.78rem", color: "var(--ink)" }}
          disabled={pending}
          onClick={() => go("pending", "未読に戻しました")}
        >
          未読に戻す
        </button>
      </div>
    );
  }

  return (
    <div className="triage-actions" style={{ marginLeft: "auto" }}>
      <button
        type="button"
        className="btn"
        style={{ padding: "4px 10px", fontSize: "0.78rem", color: "var(--ink)" }}
        disabled={pending}
        onClick={() => go("skipped", "スキップしました")}
      >
        スキップ
      </button>
      <SnoozeMenu
        disabled={pending}
        onInstant={() => go("snoozed", "後でにしました")}
        onPick={(preset: SnoozePreset, untilIso: string) =>
          go("snoozed", `後で（${formatSnoozeUntil(untilIso)}）`, {
            snoozeUntil: untilIso,
          })
        }
      />
    </div>
  );
}
