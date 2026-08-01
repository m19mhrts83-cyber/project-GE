"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { skipAllNonPartnerPending } from "@/app/actions/triage";

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
  const [pending, start] = useTransition();

  if (pendingCount <= 0) return null;

  function onClick() {
    const actionNote =
      actionCandidateCount > 0
        ? `（対応候補 ${actionCandidateCount} 件含む）`
        : "";
    const ok = window.confirm(
      `パートナー以外の未読 ${pendingCount} 件をスキップします${actionNote}。\n残したいものは先に開いて処置してください。よろしいですか？`,
    );
    if (!ok) return;
    start(async () => {
      const r = await skipAllNonPartnerPending(path);
      if (!r.ok) alert(r.error);
      else {
        if (r.message) {
          /* refresh で件数が消えるので alert は短く */
        }
        router.refresh();
      }
    });
  }

  return (
    <button
      type="button"
      className={className || "btn bulk-skip-btn"}
      disabled={pending}
      onClick={onClick}
    >
      {pending ? "スキップ中…" : `未読を一括スキップ（${pendingCount}）`}
    </button>
  );
}
