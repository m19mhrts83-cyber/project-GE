"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import {
  saveContextNote,
  type QuietEdgeResult,
} from "@/app/actions/quietEdge";
import type { ContextNoteRow, QuietEdgeAsk } from "@/lib/quietEdgeContext";

export default function QuietEdgeAskPanel({
  asks,
  notes,
}: {
  asks: QuietEdgeAsk[];
  notes: ContextNoteRow[];
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const recentNotes = [...notes]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 8);

  function keyOf(a: QuietEdgeAsk) {
    return `${a.recorded_at}|${a.trigger}`;
  }

  function submit(a: QuietEdgeAsk) {
    const k = keyOf(a);
    const answer = (drafts[k] || "").trim();
    if (!answer) {
      setErr("回答を入力してください");
      return;
    }
    setErr(null);
    setMsg(null);
    start(async () => {
      const r: QuietEdgeResult = await saveContextNote({
        recorded_at: a.recorded_at,
        trigger: a.trigger,
        prompt: a.prompt,
        answer,
      });
      if (!r.ok) {
        setErr(r.error);
        return;
      }
      setDrafts((d) => {
        const next = { ...d };
        delete next[k];
        return next;
      });
      setMsg(`${a.recorded_at} の補完を保存しました`);
      router.refresh();
    });
  }

  return (
    <section className="card qe-ask-panel">
      <header>
        <span className="lvl">Ask</span>
        <strong>そこに対して何がありましたか？</strong>
      </header>
      <p className="meta">
        Journal 欠落やいびき急変の日だけ聞きます。短いメモで十分。蓄積は観察レビューに使います。
      </p>

      {!asks.length ? (
        <p className="sum">いま未回答の問いはありません。</p>
      ) : (
        <ul className="qe-ask-list">
          {asks.map((a) => {
            const k = keyOf(a);
            return (
              <li key={k}>
                <p className="qe-ask-prompt">{a.prompt}</p>
                <p className="meta">理由: {a.reason}</p>
                <textarea
                  rows={3}
                  disabled={pending}
                  value={drafts[k] || ""}
                  placeholder="例: 飲み会あり／鼻詰まり／残業で遅い就寝…"
                  onChange={(e) =>
                    setDrafts((d) => ({ ...d, [k]: e.target.value }))
                  }
                />
                <div className="qe-form-actions">
                  <button
                    type="button"
                    className="btn"
                    disabled={pending}
                    onClick={() => submit(a)}
                  >
                    保存
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {err ? <p className="qe-err">{err}</p> : null}
      {msg ? <p className="qe-ok">{msg}</p> : null}

      {recentNotes.length ? (
        <div className="qe-notes-recent">
          <p className="meta">直近の補完メモ</p>
          <ul>
            {recentNotes.map((n) => (
              <li key={n.id}>
                <strong>{n.recorded_at}</strong>
                <span className="meta"> · {n.trigger}</span>
                <p className="sum">{n.answer}</p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
