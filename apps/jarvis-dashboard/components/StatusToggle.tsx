"use client";

import { useRouter } from "next/navigation";
import { useOptimistic, useTransition } from "react";
import { setCardStatus, setWatchStatus } from "@/app/actions/archive";
import { useToast } from "@/components/Toast";

type Props = {
  table: "cards" | "watch_status";
  id: string;
  status: string;
  path: string;
  neverArchive?: boolean;
};

export default function StatusToggle({
  table,
  id,
  status,
  path,
  neverArchive,
}: Props) {
  const router = useRouter();
  const toast = useToast();
  const [pending, start] = useTransition();
  const [optimisticStatus, setOptimistic] = useOptimistic(status);

  if (neverArchive) {
    return (
      <span
        className="meta"
        style={{ marginLeft: "auto", fontSize: "0.78rem" }}
      >
        常駐
      </span>
    );
  }

  const archived = optimisticStatus === "archived";
  const next = archived ? ("active" as const) : ("archived" as const);
  const label = archived ? "再表示" : "アーカイブ";

  function onClick() {
    start(async () => {
      setOptimistic(next);
      try {
        if (table === "cards") {
          await setCardStatus(id, next, path);
        } else {
          await setWatchStatus(id, next, path);
        }
        toast.push(archived ? "再表示しました" : "アーカイブしました");
      } catch (e) {
        toast.push(e instanceof Error ? e.message : "更新に失敗しました", "err");
      }
      router.refresh();
    });
  }

  return (
    <div style={{ marginLeft: "auto" }}>
      <button
        type="button"
        className="btn"
        style={{ padding: "4px 10px", fontSize: "0.78rem", color: "var(--ink)" }}
        disabled={pending}
        onClick={onClick}
      >
        {pending ? "…" : label}
      </button>
    </div>
  );
}
