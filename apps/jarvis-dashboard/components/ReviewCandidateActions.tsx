"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { judgeRuleCandidate } from "@/app/actions/weeklyReview";
import { useToast } from "@/components/Toast";
import { candidateOptions, type RuleCandidate, type Verdict } from "@/lib/weeklyReview";

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
  decidedOption,
}: {
  candidate: RuleCandidate;
  decided: string | null;
  decidedOption?: string | null;
}) {
  const router = useRouter();
  const toast = useToast();
  const [pending, start] = useTransition();
  const [done, setDone] = useState<string | null>(decided);
  const [doneOpt, setDoneOpt] = useState<string | null>(decidedOption || null);
  const opts = candidateOptions(candidate);
  const [pick, setPick] = useState(opts[0].id);
  const [note, setNote] = useState("");
  const chosen = opts.find((o) => o.id === pick) || opts[0];

  function send(v: Verdict) {
    start(async () => {
      const r = await judgeRuleCandidate(candidate, v, newKey(candidate.id), note, v === "accept" ? chosen.id : undefined);
      if (!r.ok) {
        toast.push(r.error, "err");
        return;
      }
      setNote("");
      if (v !== "comment") {
        setDone({ accept: "rule_accept", once: "rule_once", reject: "rule_reject" }[v]);
        setDoneOpt(v === "accept" && opts.length > 1 ? chosen.label : null);
      }
      toast.push(note.trim() && v !== "comment" ? `${TOAST[v]}（ひとことも残しました）` : TOAST[v]);
      router.refresh();
    });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
      {done ? (
        <p className="sub" style={{ margin: 0 }}>
          判断済み: <b>{LABEL[done] || done}</b>
          {doneOpt ? `（${doneOpt}）` : ""}
          （変えるときは下のボタンでもう一度）
        </p>
      ) : null}
      {opts.length > 1 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="sub">どう効かせる？</span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }} role="radiogroup">
            {opts.map((o) => (
              <button
                key={o.id}
                type="button"
                role="radio"
                aria-checked={o.id === pick}
                className={o.id === pick ? "btn primary" : "btn ghost"}
                disabled={pending}
                onClick={() => setPick(o.id)}
              >
                {o.label}
              </button>
            ))}
          </div>
          <p className="sub" style={{ margin: 0 }}>→ {chosen.text}</p>
        </div>
      ) : null}
      <textarea
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={2}
        maxLength={2000}
        placeholder="ひとこと（任意）。押した判断と一緒に残り、土曜の314が次の案に反映します。例: 請求書だけは出してほしい"
        style={{ width: "100%", padding: 8, borderRadius: 8, font: "inherit" }}
      />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <button className="btn primary" disabled={pending} onClick={() => send("accept")}>
          {opts.length > 1 ? `「${chosen.label}」で採用` : "採用する"}
        </button>
        <button className="btn" disabled={pending} onClick={() => send("once")}>
          今回だけ
        </button>
        <button className="btn" disabled={pending} onClick={() => send("reject")}>
          違う
        </button>
        <button className="btn ghost" disabled={pending || !note.trim()} onClick={() => send("comment")}>
          ひとことだけ残す
        </button>
      </div>
    </div>
  );
}
