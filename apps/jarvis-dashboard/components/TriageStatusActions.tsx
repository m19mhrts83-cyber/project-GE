"use client";

import { useRouter } from "next/navigation";
import { useOptimistic, useTransition } from "react";
import { setTriageStatus } from "@/app/actions/triage";
import type { TriageStatus } from "@/lib/triageStatus";
import { STATUS_LABEL, isUnread } from "@/lib/triageStatus";
import { useToast } from "@/components/Toast";

type Props = {
  id: string;
  status: string;
  path: string;
  /** 未読カード用: スキップ／後で。処理済み用: 未読に戻す */
  mode?: "unread" | "closed";
};

export default function TriageStatusActions({
  id,
  status,
  path,
  mode,
}: Props) {
  const router = useRouter();
  const toast = useToast();
  const [pending, start] = useTransition();
  const [optimisticStatus, setOptimistic] = useOptimistic(status);
  const unread = isUnread(optimisticStatus);
  const view = mode || (unread ? "unread" : "closed");

  function go(next: TriageStatus, label: string) {
    start(async () => {
      setOptimistic(next);
      const r = await setTriageStatus(id, next, path);
      if (!r.ok) {
        toast.push(r.error, "err");
        router.refresh();
        return;
      }
      toast.push(label);
      router.refresh();
    });
  }

  if (view === "closed") {
    return (
      <div className="triage-actions" style={{ marginLeft: "auto" }}>
        <span className={`status-badge status-${optimisticStatus}`}>
          {STATUS_LABEL[optimisticStatus as TriageStatus] || optimisticStatus}
        </span>
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
      <button
        type="button"
        className="btn"
        style={{ padding: "4px 10px", fontSize: "0.78rem", color: "var(--ink)" }}
        disabled={pending}
        onClick={() => go("snoozed", "後でにしました")}
      >
        後で
      </button>
    </div>
  );
}
