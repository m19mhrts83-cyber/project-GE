"use client";

import { useState, useTransition } from "react";
import { addMaturityTask } from "@/app/actions/agentMaturity";

/** 優先改善をTodoistへ（🦾依頼）。押したら結果とリンクを出す */
export default function MaturityTaskButton({ itemKey, actionIndex, why }: { itemKey: string; actionIndex: number; why: string }) {
  const [pending, start] = useTransition();
  const [msg, setMsg] = useState<{ ok: boolean; text: string; url?: string } | null>(null);
  if (msg?.ok) {
    return (
      <span className="mat-done">
        {msg.text}{" "}
        {msg.url ? (
          <a href={msg.url} target="_blank" rel="noopener noreferrer">
            Todoistで開く ↗
          </a>
        ) : null}
      </span>
    );
  }
  return (
    <span className="mat-btn-wrap">
      <button
        type="button"
        className="btn"
        disabled={pending}
        onClick={() =>
          start(async () => {
            const r = await addMaturityTask(itemKey, actionIndex, why);
            setMsg(r.ok ? { ok: true, text: r.duplicate ? "登録済みでした" : "Todoistに入れました", url: r.url } : { ok: false, text: r.error });
          })
        }
      >
        {pending ? "登録中…" : "Todoistへ"}
      </button>
      {msg && !msg.ok ? <span className="mat-err" role="alert">{msg.text}</span> : null}
    </span>
  );
}
