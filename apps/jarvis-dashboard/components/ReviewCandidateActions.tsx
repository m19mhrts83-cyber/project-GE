"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { judgeRuleCandidate } from "@/app/actions/weeklyReview";
import { useToast } from "@/components/Toast";
import type { RuleCandidate, Verdict } from "@/lib/weeklyReview";

const LABEL: Record<string, string> = {
  rule_accept: "採用した",
  rule_once: "今回だけにした",
  rule_reject: "違うにした",
};

const TOAST: Record<Verdict, string> = {
  accept: "採用しました。土曜の314がルール帳に反映します",
  once: "今回だけにしました（ルールにはしません）",
  reject: "違うにしました。この候補は8週間出しません",
  comment: "ひとことを残しました。土曜の314が修正案に反映します",
};

function newKey(id: string): string {
  const r =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `review:${id}:${r}`;
}

export default function ReviewCandidateActions({
  candidate,
  decided,
}: {
  candidate: RuleCandidate;
  decided: string | null;
}) {
  const router = useRouter();
  const toast = useToast();
  const [pending, start] = useTransition();
  const [done, setDone] = useState<string | null>(decided);
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");

  function send(v: Verdict) {
    start(async () => {
      const r = await judgeRuleCandidate(candidate, v, newKey(candidate.id), v === "comment" ? note : undefined);
      if (!r.ok) {
        toast.push(r.error, "err");
        return;
      }
      if (v === "comment") {
        setNote("");
        setOpen(false);
      } else {
        setDone({ accept: "rule_accept", once: "rule_once", reject: "rule_reject" }[v]);
      }
      toast.push(TOAST[v]);
      router.refresh();
    });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
      {done ? (
        <p className="sub" style={{ margin: 0 }}>
          判断済み: <b>{LABEL[done] || done}</b>
          （変えるときは下のボタンでもう一度）
        </p>
      ) : null}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button className="btn primary" disabled={pending} onClick={() => send("accept")}>
          採用する
        </button>
        <button className="btn" disabled={pending} onClick={() => send("once")}>
          今回だけ
        </button>
        <button className="btn" disabled={pending} onClick={() => send("reject")}>
          違う
        </button>
        <button className="btn ghost" disabled={pending} onClick={() => setOpen((o) => !o)}>
          直してひとこと
        </button>
      </div>
      {open ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={3}
            maxLength={2000}
            placeholder="例: このアドレスは請求書だけ見送り、それ以外は出してほしい"
            style={{ width: "100%", padding: 8, borderRadius: 8, font: "inherit" }}
          />
          <div>
            <button className="btn primary" disabled={pending || !note.trim()} onClick={() => send("comment")}>
              ひとことを残す
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
