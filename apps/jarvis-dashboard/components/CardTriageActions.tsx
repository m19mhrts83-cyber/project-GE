"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import {
  askJarvisOnCard,
  postCardComment,
  promoteCardToNotion,
  skipCard,
} from "@/app/actions/cardKanban";

export type CardCommentRow = {
  id: number;
  role: string;
  body: string;
  created_at: string;
};

type CardRow = {
  id: string;
  title: string;
  summary: string | null;
  status: string;
  kind: string;
  cursor_prompt: string | null;
  payload: Record<string, unknown> | null;
};

function fmtAt(v: string) {
  const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (m) return `${m[2]}/${m[3]} ${m[4]}:${m[5]}`;
  return String(v).slice(0, 16);
}

export default function CardTriageActions({
  card,
  lane,
  path,
  comments,
}: {
  card: CardRow;
  lane: string;
  path: string;
  comments: CardCommentRow[];
}) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const notionUrl =
    typeof card.payload?.notion_url === "string"
      ? card.payload.notion_url
      : null;

  function run(
    kind: "skip" | "promote" | "post" | "ask",
  ) {
    setErr(null);
    setMsg(null);
    start(async () => {
      let r;
      if (kind === "skip") r = await skipCard(card.id, path);
      else if (kind === "promote")
        r = await promoteCardToNotion(card.id, lane, path);
      else if (kind === "ask") r = await askJarvisOnCard(card.id, text, path);
      else r = await postCardComment(card.id, text, path);
      if (!r.ok) {
        setErr(r.error || "失敗しました");
        return;
      }
      setMsg(r.message || "完了");
      if (kind === "post" || kind === "ask") setText("");
      router.refresh();
    });
  }

  return (
    <div className="card-triage">
      {card.status === "active" ? (
        <div className="card-triage-btns">
          <button
            type="button"
            className="btn"
            disabled={pending}
            onClick={() => run("skip")}
          >
            {card.kind === "digest" ? "見送り" : "スキップ"}
          </button>
          <button
            type="button"
            className="btn"
            disabled={pending}
            onClick={() => run("promote")}
            style={{ fontWeight: 700 }}
          >
            {card.kind === "digest" ? "タスク化する" : "処置として進める"}
          </button>
        </div>
      ) : null}
      {notionUrl ? (
        <p className="meta">
          Notion:{" "}
          <a href={notionUrl} target="_blank" rel="noreferrer">
            タスクを開く
          </a>
        </p>
      ) : null}
      <div className="watch-comments">
        <p className="watch-comments-title">コメント（Jarvisに聞ける）</p>
        {comments.length === 0 ? (
          <p className="meta" style={{ margin: "0 0 8px" }}>
            方針や期限の相談ができます。
          </p>
        ) : (
          <ul className="watch-comment-list">
            {comments.map((c) => (
              <li
                key={c.id}
                className={`watch-comment ${c.role === "jarvis" ? "jarvis" : "user"}`}
              >
                <header>
                  <strong>{c.role === "jarvis" ? "Jarvis" : "あなた"}</strong>
                  <span className="meta">{fmtAt(c.created_at)}</span>
                </header>
                <p>{c.body}</p>
              </li>
            ))}
          </ul>
        )}
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          placeholder="コメント or Jarvisへの質問"
          style={{ width: "100%", marginTop: 8 }}
        />
        <div className="card-triage-btns" style={{ marginTop: 6 }}>
          <button
            type="button"
            className="btn"
            disabled={pending}
            onClick={() => run("post")}
          >
            コメント
          </button>
          <button
            type="button"
            className="btn"
            disabled={pending}
            onClick={() => run("ask")}
          >
            Jarvisに聞く
          </button>
        </div>
      </div>
      {err ? <p className="err">{err}</p> : null}
      {msg ? <p className="meta">{msg}</p> : null}
    </div>
  );
}
