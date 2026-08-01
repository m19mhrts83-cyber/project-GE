"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { setTriageStatus } from "@/app/actions/triage";
import type { TriageStatus } from "@/lib/triageStatus";
import { STATUS_LABEL, isUnread } from "@/lib/triageStatus";

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
  const [pending, start] = useTransition();
  const unread = isUnread(status);
  const view = mode || (unread ? "unread" : "closed");

  function go(next: TriageStatus) {
    start(async () => {
      const r = await setTriageStatus(id, next, path);
      if (!r.ok) alert(r.error);
      else router.refresh();
    });
  }

  if (view === "closed") {
    return (
      <div className="triage-actions" style={{ marginLeft: "auto" }}>
        <span className={`status-badge status-${status}`}>
          {STATUS_LABEL[status as TriageStatus] || status}
        </span>
        <button
          type="button"
          className="btn"
          style={{ padding: "4px 10px", fontSize: "0.78rem" }}
          disabled={pending}
          onClick={() => go("pending")}
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
        style={{ padding: "4px 10px", fontSize: "0.78rem" }}
        disabled={pending}
        onClick={() => go("skipped")}
      >
        スキップ
      </button>
      <button
        type="button"
        className="btn"
        style={{ padding: "4px 10px", fontSize: "0.78rem" }}
        disabled={pending}
        onClick={() => go("snoozed")}
      >
        後で
      </button>
    </div>
  );
}
