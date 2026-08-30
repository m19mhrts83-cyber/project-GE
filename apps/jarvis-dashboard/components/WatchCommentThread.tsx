"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import {
  askJarvisOnWatch,
  enqueueWatchCursorAsk,
  getWatchCursorAskStatus,
  postWatchComment,
} from "@/app/actions/watchComments";
import type { AskEngine } from "@/lib/askEngineTypes";
import { defaultAskContextSources } from "@/lib/askContextBundle";
import { buildLocalHandoffPrompt } from "@/lib/localHandoff";
import LocalHandoffBar from "@/components/LocalHandoffBar";
import { formatJstMmDdHm } from "@/lib/formatJst";

export type WatchCommentRow = {
  id: number;
  role: string;
  body: string;
  created_at: string;
};

export default function WatchCommentThread({
  watchId,
  title = "",
  summary = null,
  detail = null,
  cursorPrompt = null,
  payload = null,
  comments,
  path = "/situation",
}: {
  watchId: string;
  title?: string;
  summary?: string | null;
  detail?: string | null;
  cursorPrompt?: string | null;
  payload?: Record<string, unknown> | null;
  comments: WatchCommentRow[];
  path?: string;
}) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [notices, setNotices] = useState<string[]>([]);
  const [localPrompt, setLocalPrompt] = useState("");
  const [needLocal, setNeedLocal] = useState(false);
  const [engine, setEngine] = useState<AskEngine>("cursor");
  const contextLane =
    typeof payload?.lane === "string" ? payload.lane : null;
  const [useKamiooya, setUseKamiooya] = useState(
    () => defaultAskContextSources(contextLane).kamiooya,
  );
  const [useOnedrive, setUseOnedrive] = useState(
    () => defaultAskContextSources(contextLane).onedriveYoritoori,
  );
  const [useGdrive, setUseGdrive] = useState(
    () => defaultAskContextSources(contextLane).gdrive,
  );
  const [pending, start] = useTransition();
  const [macPolling, setMacPolling] = useState(() => {
    const ask = payload?.cursor_ask;
    if (ask && typeof ask === "object") {
      const st = (ask as { status?: string }).status;
      return st === "queued" || st === "running";
    }
    return false;
  });

  const defaultHandoff = useMemo(() => {
    const pl = payload || {};
    const actions = Array.isArray(pl.actions) ? pl.actions : [];
    const actionLines = actions
      .slice(0, 20)
      .map((a) => {
        if (!a || typeof a !== "object") return "";
        const row = a as Record<string, unknown>;
        return String(row.line || `${row.date} / ${row.shop} / ¥${row.amount}`);
      })
      .filter(Boolean);
    return buildLocalHandoffPrompt({
      kind: "watch",
      id: watchId,
      title: title || watchId,
      summary,
      detail,
      bullets: actionLines,
      cursorPrompt,
      comments: comments.map((c) => ({ role: c.role, body: c.body })),
      lastUserMessage: text.trim() || null,
    });
  }, [watchId, title, summary, detail, cursorPrompt, payload, comments, text]);

  useEffect(() => {
    if (!macPolling) return;
    let cancelled = false;
    const tick = async () => {
      const r = await getWatchCursorAskStatus(watchId);
      if (cancelled || !r.ok) return;
      const st = r.ask?.status;
      if (st === "done") {
        setMacPolling(false);
        setMsg("Mac のローカル Cursor から返答が付きました");
        setNotices(["Mac のローカル Cursor から返答が付きました"]);
        router.refresh();
        return;
      }
      if (st === "error") {
        setMacPolling(false);
        setErr(r.ask?.error || "Mac Worker が失敗しました");
        setNeedLocal(true);
        setNotices([
          "Mac Worker が失敗したため、ローカル用コピーで引き継げます",
        ]);
      }
    };
    const id = window.setInterval(() => void tick(), 4000);
    void tick();
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [macPolling, watchId, router]);

  function run(kind: "post" | "ask") {
    const body = text.trim();
    if (!body) {
      setErr("コメントを入力してください");
      return;
    }
    setErr(null);
    setMsg(null);
    if (kind !== "ask") setNotices([]);
    start(async () => {
      if (kind === "post") {
        const r = await postWatchComment(watchId, body, path);
        if (!r.ok) {
          setErr(r.error || "失敗しました");
          return;
        }
        setMsg(r.message || "完了");
        setText("");
        router.refresh();
        return;
      }
      const r = await askJarvisOnWatch(watchId, body, path, engine, {
        useKamiooyaKnowledge: useKamiooya,
        useOnedriveYoritoori: useOnedrive,
        useGdrive,
      });
      setNotices(r.fallbackNotices || []);
      if (r.localPrompt) setLocalPrompt(r.localPrompt);
      if (!r.ok) {
        setNeedLocal(Boolean(r.needLocal));
        setErr(r.error || "失敗しました");
        setMsg(r.message || null);
        router.refresh();
        return;
      }
      setNeedLocal(false);
      setMsg(r.message || "完了");
      setText("");
      router.refresh();
    });
  }

  return (
    <div className="watch-comments" suppressHydrationWarning>
      <p className="watch-comments-title" suppressHydrationWarning>
        コメント（エンジンを選んで聞ける）
      </p>
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
                <span className="meta">{formatJstMmDdHm(c.created_at)}</span>
              </header>
              <p>{c.body}</p>
            </li>
          ))}
        </ul>
      )}
      <fieldset className="draft-engine" style={{ marginTop: 10 }}>
        <legend>聞くエンジン</legend>
        <label className="draft-engine-opt">
          <input
            type="radio"
            name={`watch-ask-engine-${watchId}`}
            checked={engine === "cursor"}
            onChange={() => setEngine("cursor")}
            disabled={pending || macPolling}
          />
          Jarvis Cloud
        </label>
        <label className="draft-engine-opt">
          <input
            type="radio"
            name={`watch-ask-engine-${watchId}`}
            checked={engine === "gemini"}
            onChange={() => setEngine("gemini")}
            disabled={pending || macPolling}
          />
          Gemini
        </label>
      </fieldset>
      {engine === "cursor" ? (
        <p className="meta" style={{ margin: "6px 0 0" }}>
          既定は Jarvis Cloud。失敗時は Gemini に自動切替し、その旨を表示します。
        </p>
      ) : null}
      <label
        className="draft-engine-opt"
        style={{ display: "flex", marginTop: 8, gap: 8 }}
      >
        <input
          type="checkbox"
          checked={useKamiooya}
          onChange={(e) => setUseKamiooya(e.target.checked)}
          disabled={pending || macPolling}
        />
        神大家ナレッジを参照（コメント・動画／kamiooya-qa）
      </label>
      <label
        className="draft-engine-opt"
        style={{ display: "flex", marginTop: 6, gap: 8 }}
      >
        <input
          type="checkbox"
          checked={useOnedrive}
          onChange={(e) => setUseOnedrive(e.target.checked)}
          disabled={pending || macPolling}
        />
        OneDriveやり取り末尾を参照（5.やり取り.md／Graph）
      </label>
      <label
        className="draft-engine-opt"
        style={{ display: "flex", marginTop: 6, gap: 8 }}
        title="admin Drive の 200_NoteBookLM を検索して注入（手動オン）"
      >
        <input
          type="checkbox"
          checked={useGdrive}
          onChange={(e) => setUseGdrive(e.target.checked)}
          disabled={pending || macPolling}
        />
        Google Drive／NotebookLM を参照（200_NoteBookLM）
      </label>
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
          disabled={pending || macPolling || !text.trim()}
          onClick={() => run("ask")}
        >
          {pending
            ? "返答中…"
            : engine === "cursor"
              ? "Jarvis Cloud に聞く"
              : "Gemini に聞く"}
        </button>
      </div>

      <LocalHandoffBar
        localPrompt={localPrompt || defaultHandoff}
        notices={notices}
        forceOpen={needLocal}
        macPending={macPolling}
        onEnqueueMac={async (extraNote) => {
          const r = await enqueueWatchCursorAsk(watchId, path, {
            extraNote,
            question: text.trim() || undefined,
          });
          if (r.ok && r.queued) setMacPolling(true);
          if (r.fallbackNotices?.length) setNotices(r.fallbackNotices);
          if (r.localPrompt) setLocalPrompt(r.localPrompt);
          router.refresh();
          return r;
        }}
      />

      {err ? <p className="draft-err">{err}</p> : null}
      {msg ? <p className="draft-hint">{msg}</p> : null}
    </div>
  );
}
