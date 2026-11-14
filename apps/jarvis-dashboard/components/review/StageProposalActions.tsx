"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { judgeStage } from "@/app/actions/agentStage";
import { useToast } from "@/components/Toast";
import { verdictLabel, type StageProposal, type StageVerdict } from "@/lib/agentStageReview";

function newKey(id: string): string {
  const r =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `stage:${id}:${r}`;
}

export default function StageProposalActions({
  p,
  decided,
}: {
  p: StageProposal;
  decided: { action: string; note: string | null } | null;
}) {
  const router = useRouter();
  const toast = useToast();
  const [pending, start] = useTransition();
  const [done, setDone] = useState(decided);
  const [note, setNote] = useState("");

  function send(v: StageVerdict) {
    start(async () => {
      const r = await judgeStage(p.key, v, newKey(p.key), note);
      if (!r.ok) {
        toast.push(r.error, "err");
        return;
      }
      setDone({ action: v, note: note.trim() || null });
      setNote("");
      toast.push(
        v === "adopt"
          ? `${p.id} を${verdictLabel(v, p)}と記録しました。土曜 9:30 の 314 が登記簿とダッシュに反映します`
          : v === "skip"
            ? "見送りました。4週間はこの提案を出しません"
            : "来週もう一度出します",
      );
      router.refresh();
    });
  }

  return (
    <div className="stg-act">
      {done ? (
        <p className="sub" style={{ margin: 0 }}>
          判断済み: <b>{verdictLabel(done.action, p)}</b>
          {done.note ? `（理由: ${done.note}）` : ""}（変えるときはもう一度）
        </p>
      ) : null}
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={2}
        maxLength={2000}
        placeholder={
          p.kind === "down"
            ? "理由（任意）。例: 止まったままなので仕上げに戻す"
            : `理由（任意）。例: ${p.to === "運用" ? "2週間見て意図どおり。報告も読めている" : "定時が回り始めたので仕上げに入る"}`
        }
      />
      <div className="stg-btns">
        <button className="btn primary" disabled={pending} onClick={() => send("adopt")}>
          {verdictLabel("adopt", p)}
        </button>
        <button className="btn" disabled={pending} onClick={() => send("defer")}>
          来週また
        </button>
        <button className="btn ghost" disabled={pending} onClick={() => send("skip")}>
          見送る
        </button>
      </div>
    </div>
  );
}
