"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import {
  createGluconCarryMemo,
  discardGluconCarryMemo,
  markGluconCarryMemoUsed,
  updateGluconCarryMemo,
} from "@/app/actions/glucon";
import type {
  GluconCarryKindHint,
  GluconCarryMemo,
} from "@/lib/glucon/types";

const KIND_LABEL: Record<GluconCarryKindHint, string> = {
  result: "成果",
  activity: "活動",
  either: "どちらでも",
};

function injectLabel(memo: GluconCarryMemo, periodKey: string | null): string {
  if (memo.status !== "open") return "";
  if (!periodKey) return `次周期（${memo.available_from_period_key}〜）で注入`;
  if (memo.available_from_period_key <= periodKey) {
    return "今周期の下書き生成に注入する";
  }
  return "今月の下書きには入れない（次月から注入）";
}

export default function GluconCarryMemoPanel({
  memos,
  periodKey,
}: {
  memos: GluconCarryMemo[];
  periodKey: string | null;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [kindHint, setKindHint] = useState<GluconCarryKindHint>("result");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [showUsed, setShowUsed] = useState(false);

  const openMemos = memos.filter((m) => m.status === "open");
  const usedMemos = memos.filter((m) => m.status === "used").slice(0, 6);

  function resetForm() {
    setTitle("");
    setBody("");
    setKindHint("result");
    setEditingId(null);
  }

  return (
    <section
      className="glucon-carry"
      aria-labelledby="glucon-carry-heading"
    >
      <h2 id="glucon-carry-heading">次月報告メモ</h2>
      <p className="meta">
        今月は見送り・次月のネタにしたいことを残します。退避した周期の下書きには入れず、翌周期の活動／成果生成へ自動で入ります。未実施なら成果本文には書きません。
      </p>

      <ul className="glucon-carry-list">
        {openMemos.length === 0 ? (
          <li className="meta">開いているメモはありません。</li>
        ) : (
          openMemos.map((memo) => (
            <li key={memo.id} className="card glucon-carry-item">
              <div className="glucon-carry-item-head">
                <strong>{memo.title}</strong>
                <span className="meta">
                  {KIND_LABEL[memo.kind_hint]} ／ {injectLabel(memo, periodKey)}
                </span>
              </div>
              {memo.body ? (
                <p className="glucon-carry-body">{memo.body}</p>
              ) : null}
              <div className="qe-form-actions" style={{ gap: "0.4rem" }}>
                <button
                  type="button"
                  className="btn"
                  disabled={pending}
                  onClick={() => {
                    setEditingId(memo.id);
                    setTitle(memo.title);
                    setBody(memo.body);
                    setKindHint(memo.kind_hint);
                    setErr(null);
                  }}
                >
                  編集
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={pending}
                  onClick={() => {
                    if (
                      !window.confirm(
                        "このメモを「今回使った」にして開いている一覧から外しますか？",
                      )
                    ) {
                      return;
                    }
                    start(async () => {
                      setErr(null);
                      const r = await markGluconCarryMemoUsed(memo.id);
                      if (!r.ok) setErr(r.error || "完了にできませんでした");
                      router.refresh();
                    });
                  }}
                >
                  今回使った
                </button>
                <button
                  type="button"
                  className="btn"
                  disabled={pending}
                  onClick={() => {
                    if (!window.confirm("このメモを削除しますか？")) return;
                    start(async () => {
                      setErr(null);
                      const r = await discardGluconCarryMemo(memo.id);
                      if (!r.ok) setErr(r.error || "削除できませんでした");
                      if (editingId === memo.id) resetForm();
                      router.refresh();
                    });
                  }}
                >
                  削除
                </button>
              </div>
            </li>
          ))
        )}
      </ul>

      <form
        className="card glucon-carry-form"
        onSubmit={(e) => {
          e.preventDefault();
          start(async () => {
            setErr(null);
            if (editingId) {
              const r = await updateGluconCarryMemo(editingId, {
                title,
                body,
                kind_hint: kindHint,
              });
              if (!r.ok) {
                setErr(r.error || "更新できませんでした");
                return;
              }
            } else {
              const r = await createGluconCarryMemo({
                title,
                body,
                kind_hint: kindHint,
              });
              if (!r.ok) {
                setErr(r.error || "追加できませんでした");
                return;
              }
            }
            resetForm();
            router.refresh();
          });
        }}
      >
        <p className="meta">{editingId ? "メモを編集" : "メモを追加"}</p>
        <label className="meta">
          タイトル
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            maxLength={120}
          />
        </label>
        <label className="meta">
          本文
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={4}
          />
        </label>
        <label className="meta">
          寄せ先
          <select
            value={kindHint}
            onChange={(e) =>
              setKindHint(e.target.value as GluconCarryKindHint)
            }
          >
            <option value="result">成果報告</option>
            <option value="activity">活動報告</option>
            <option value="either">どちらでも</option>
          </select>
        </label>
        <div className="qe-form-actions" style={{ gap: "0.4rem" }}>
          <button type="submit" className="btn" disabled={pending}>
            {editingId ? "更新" : "次月メモに追加"}
          </button>
          {editingId ? (
            <button
              type="button"
              className="btn"
              disabled={pending}
              onClick={() => {
                resetForm();
                setErr(null);
              }}
            >
              キャンセル
            </button>
          ) : null}
        </div>
      </form>

      {err ? <p className="qe-err">{err}</p> : null}

      {usedMemos.length ? (
        <details
          className="glucon-carry-used"
          open={showUsed}
          onToggle={(e) => setShowUsed(e.currentTarget.open)}
        >
          <summary>完了済み（直近）</summary>
          <ul className="glucon-carry-list">
            {usedMemos.map((memo) => (
              <li key={memo.id} className="meta">
                {memo.title}
                {memo.used_in_period_key
                  ? `（${memo.used_in_period_key}）`
                  : ""}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  );
}
