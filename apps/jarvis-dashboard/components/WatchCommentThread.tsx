"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import {
  askJarvisOnWatch,
  postWatchComment,
} from "@/app/actions/watchComments";

export type WatchCommentRow = {
  id: number;
  role: string;
  body: string;
  created_at: string;
};

function fmtAt(v: string) {
  const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (m) return `${m[2]}/${m[3]} ${m[4]}:${m[5]}`;
  return String(v).slice(0, 16);
}

export default function WatchCommentThread({
  watchId,
  comments,
  path = "/situation",
}: {
  watchId: string;
  comments: WatchCommentRow[];
  path?: string;
}) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [pending, start] = useTransition();

  function run(kind: "post" | "ask") {
    const body = text.trim();
    if (!body) {
      setErr("コメントを入力してください");
      return;
    }
    setErr(null);
    setMsg(null);
    start(async () => {
      const r =
        kind === "ask"
          ? await askJarvisOnWatch(watchId, body, path)
          : await postWatchComment(watchId, body, path);
      if (!r.ok) {
        setErr(r.error || "失敗しました");
        return;
      }
      setMsg(r.message || "完了");
      setText("");
      router.refresh();
    });
  }

  return (
    <div className="watch-comments">
      <p className="watch-comments-title">コメント（Jarvisに聞ける）</p>
      {comments.length === 0 ? (
        <p className="meta" style={{ margin: "0 0 8px" }}>
          まだコメントはありません。要対応の日付や直し方について聞けます。
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
        className="watch-comment-input"
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="例: 3/8 のミニストップはどれを直せばいい？"
        disabled={pending}
      />
      <div className="watch-comment-actions">
        <button
          type="button"
          className="btn"
          style={{ color: "var(--ink)" }}
          disabled={pending}
          onClick={() => run("post")}
        >
          投稿のみ
        </button>
        <button
          type="button"
          className="btn primary"
          disabled={pending}
          onClick={() => run("ask")}
        >
          {pending ? "返答中…" : "Jarvisに聞く"}
        </button>
      </div>
      {err ? <p className="draft-err">{err}</p> : null}
      {msg ? <p className="draft-hint">{msg}</p> : null}
    </div>
  );
}
