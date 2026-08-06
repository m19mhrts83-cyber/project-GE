"use client";

import { useRouter } from "next/navigation";
import { useOptimistic, useTransition } from "react";
import { skipAllNonPartnerPending } from "@/app/actions/triage";
import { useToast } from "@/components/Toast";

type Props = {
  path: string;
  pendingCount: number;
  actionCandidateCount?: number;
  className?: string;
};

export default function BulkSkipNonPartnerButton({
  path,
  pendingCount,
  actionCandidateCount = 0,
  className,
}: Props) {
  const router = useRouter();
  const toast = useToast();
  const [pending, start] = useTransition();
  const [optimisticCount, setOptimisticCount] = useOptimistic(pendingCount);

  if (optimisticCount <= 0) return null;

  function onClick() {
    const actionNote =
      actionCandidateCount > 0
        ? `（対応候補 ${actionCandidateCount} 件含む）`
        : "";
    const ok = window.confirm(
      `パートナー以外の未読 ${optimisticCount} 件をスキップします${actionNote}。\n残したいものは先に開いて処置してください。よろしいですか？`,
    );
    if (!ok) return;
    start(async () => {
      setOptimisticCount(0);
      const r = await skipAllNonPartnerPending(path);
      if (!r.ok) {
        toast.push(r.error, "err");
        router.refresh();
        return;
      }
      toast.push(r.message || "スキップしました");
      router.refresh();
    });
  }

  return (
    <button
      type="button"
      className={className || "btn bulk-skip-btn"}
      disabled={pending}
      onClick={onClick}
    >
      {pending ? "スキップ中…" : `未読を一括スキップ（${optimisticCount}）`}
    </button>
  );
}
