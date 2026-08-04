"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import {
  askJarvisOnCard,
  enqueueCardCursorAsk,
  getCardCursorAskStatus,
  postCardComment,
  promoteCardToNotion,
  skipCard,
} from "@/app/actions/cardKanban";
import type { AskEngine } from "@/lib/askEngineTypes";
import {
  buildLocalHandoffPrompt,
} from "@/lib/localHandoff";
import { defaultAskContextSources } from "@/lib/askContextBundle";
import { formatJstMmDdHm } from "@/lib/formatJst";
import { NOTION_TASK_LANES, guessPropertyName } from "@/lib/notionTaskDbs";
import {
  fetchPropertySelectOptionsAction,
} from "@/app/actions/notionBoard";
import LocalHandoffBar from "@/components/LocalHandoffBar";

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

function defaultPromoteTitle(card: CardRow): string {
  return card.title.replace(/^\[確認\]\s*/, "").trim() || card.title;
}

function defaultPromoteSummary(card: CardRow): string {
  const payload = card.payload || {};
  if (typeof payload.question === "string" && payload.question.trim()) {
    const bullets = Array.isArray(payload.bullets)
      ? (payload.bullets as unknown[]).map((b) => String(b)).join("\n")
      : "";
    return [payload.question.trim(), bullets].filter(Boolean).join("\n").slice(0, 1800);
  }
  return (card.summary || "").slice(0, 1800);
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
  const isDigest = card.kind === "digest";
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [notices, setNotices] = useState<string[]>([]);
  const [localPrompt, setLocalPrompt] = useState<string>("");
  const [needLocal, setNeedLocal] = useState(false);
  const [engine, setEngine] = useState<AskEngine>("cursor");
  const [useKamiooya, setUseKamiooya] = useState(
    () => defaultAskContextSources(lane).kamiooya,
  );
  const [useOnedrive, setUseOnedrive] = useState(
    () => defaultAskContextSources(lane).onedriveYoritoori,
  );
  const [pending, start] = useTransition();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [promoTitle, setPromoTitle] = useState(() => defaultPromoteTitle(card));
  const [promoSummary, setPromoSummary] = useState(() =>
    defaultPromoteSummary(card),
  );
  const [propertyOptions, setPropertyOptions] = useState<string[]>([]);
  const [promoProperty, setPromoProperty] = useState("");
  const needsProperty = Boolean(NOTION_TASK_LANES[lane]?.property_prop);
  const [macPolling, setMacPolling] = useState(() => {
    const ask = card.payload?.cursor_ask;
    if (ask && typeof ask === "object") {
      const st = (ask as { status?: string }).status;
      return st === "queued" || st === "running";
    }
    return false;
  });

  const notionUrl =
    typeof card.payload?.notion_url === "string"
      ? card.payload.notion_url
      : null;

  const defaultHandoff = useMemo(() => {
    const payload = card.payload || {};
    const question =
      typeof payload.question === "string" ? payload.question : "";
    const bullets = Array.isArray(payload.bullets)
      ? (payload.bullets as unknown[]).map((b) => String(b)).slice(0, 20)
      : [];
    return buildLocalHandoffPrompt({
      kind: "card",
      id: card.id,
      title: card.title,
      summary: card.summary,
      question,
      bullets,
      lane,
      cursorPrompt: card.cursor_prompt,
      comments: comments.map((c) => ({ role: c.role, body: c.body })),
      lastUserMessage: text.trim() || null,
    });
  }, [card, comments, lane, text]);

  const explain = useMemo(() => {
    if (isDigest) {
      return "流れ: コメントで方針を相談 → 納得したら「タスク化する」で内容確認 → Notion 看板に1件登録。押した瞬間に作られることはありません。";
    }
    return "「処置として進める」は Notion にタスクを1件作ります。先に内容確認画面が出ます。";
  }, [isDigest]);

  useEffect(() => {
    if (!macPolling) return;
    let cancelled = false;
    const tick = async () => {
      const r = await getCardCursorAskStatus(card.id);
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
  }, [macPolling, card.id, router]);

  function openConfirm() {
    setErr(null);
    setMsg(null);
    setPromoTitle(defaultPromoteTitle(card));
    setPromoSummary(defaultPromoteSummary(card));
    setConfirmOpen(true);
    if (needsProperty) {
      void (async () => {
        const r = await fetchPropertySelectOptionsAction(lane);
        const opts = r.ok ? r.options : [];
        setPropertyOptions(opts);
        const guessed = guessPropertyName(
          [card.title, card.summary || "", defaultPromoteTitle(card)].join(
            "\n",
          ),
          opts,
        );
        setPromoProperty(guessed);
      })();
    } else {
      setPromoProperty("");
      setPropertyOptions([]);
    }
  }

  function run(kind: "skip" | "promote" | "post" | "ask") {
    setErr(null);
    setMsg(null);
    if (kind !== "ask") setNotices([]);
    start(async () => {
      if (kind === "skip") {
        const r = await skipCard(card.id, path);
        if (!r.ok) {
          setErr(r.error || "失敗しました");
          return;
        }
        setMsg(r.message || "完了");
        router.refresh();
        return;
      }
      if (kind === "promote") {
        if (needsProperty && !promoProperty.trim()) {
          setErr("物件名（サブグループ）を選択してください");
          return;
        }
        const r = await promoteCardToNotion(card.id, lane, path, {
          title: promoTitle.trim() || defaultPromoteTitle(card),
          summary: promoSummary.trim(),
          propertyName: promoProperty.trim() || undefined,
        });
        if (!r.ok) {
          setErr(r.error || "失敗しました");
          return;
        }
        setMsg(r.message || "完了");
        setConfirmOpen(false);
        router.refresh();
        return;
      }
      if (kind === "post") {
        const r = await postCardComment(card.id, text, path);
        if (!r.ok) {
          setErr(r.error || "失敗しました");
          return;
        }
        setMsg(r.message || "完了");
        setText("");
        router.refresh();
        return;
      }

      const r = await askJarvisOnCard(card.id, text, path, engine, {
        useKamiooyaKnowledge: useKamiooya,
        useOnedriveYoritoori: useOnedrive,
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

  const handoffPrompt = localPrompt || defaultHandoff;

  return (
    <div className={`card-triage${isDigest ? " is-digest" : ""}`}>
      <p className="meta digest-flow-hint">{explain}</p>
      {card.status === "active" ? (
        <div className="card-triage-btns digest-actions">
          <button
            type="button"
            className="btn"
            disabled={pending}
            onClick={() => run("skip")}
          >
            {isDigest ? "見送り" : "スキップ"}
          </button>
          <button
            type="button"
            className="btn primary"
            disabled={pending}
            onClick={openConfirm}
          >
            {isDigest ? "タスク化する…" : "処置として進める…"}
          </button>
        </div>
      ) : null}

      {confirmOpen && card.status === "active" ? (
        <div className="promote-confirm">
          <p className="promote-confirm-title">
            Notion に登録する内容（まだ作成していません）
          </p>
          <p className="meta" style={{ margin: "0 0 8px" }}>
            レーン「{lane}」の看板に<strong>未着手</strong>で1件追加します。タイトルは編集できます。
          </p>
          <label className="promote-label">
            タスク名
            <input
              type="text"
              value={promoTitle}
              onChange={(e) => setPromoTitle(e.target.value)}
              disabled={pending}
            />
          </label>
          {needsProperty ? (
            <label className="promote-label">
              物件名（Notion サブグループ）
              <select
                value={promoProperty}
                onChange={(e) => setPromoProperty(e.target.value)}
                disabled={pending}
              >
                <option value="">選択してください</option>
                {propertyOptions.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
                {promoProperty &&
                !propertyOptions.includes(promoProperty) ? (
                  <option value={promoProperty}>{promoProperty}</option>
                ) : null}
              </select>
            </label>
          ) : null}
          <label className="promote-label">
            本文（Notion の説明）
            <textarea
              value={promoSummary}
              onChange={(e) => setPromoSummary(e.target.value)}
              rows={5}
              disabled={pending}
            />
          </label>
          <div className="card-triage-btns" style={{ marginTop: 8 }}>
            <button
              type="button"
              className="btn"
              disabled={pending}
              onClick={() => setConfirmOpen(false)}
            >
              やめる
            </button>
            <button
              type="button"
              className="btn primary"
              disabled={
                pending ||
                !promoTitle.trim() ||
                (needsProperty && !promoProperty.trim())
              }
              onClick={() => run("promote")}
            >
              この内容で Notion に登録
            </button>
          </div>
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
        <p className="watch-comments-title">
          {isDigest
            ? "相談（過去のやり取りを踏まえて返答）"
            : "コメント（エンジンを選んで聞ける）"}
        </p>
        {comments.length === 0 ? (
          <p className="meta" style={{ margin: "0 0 8px" }}>
            {isDigest
              ? "「何をタスクにするか」をここで相談できます。先にやり取りしてからタスク化してください。"
              : "方針や期限の相談ができます。"}
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
              name={`ask-engine-${card.id}`}
              checked={engine === "cursor"}
              onChange={() => setEngine("cursor")}
              disabled={pending || macPolling}
            />
            Jarvis Cloud
          </label>
          <label className="draft-engine-opt">
            <input
              type="radio"
              name={`ask-engine-${card.id}`}
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
          style={{
            display: "flex",
            marginTop: 6,
            gap: 8,
            opacity: 0.65,
          }}
          title="Phase3。Cloud 対話は NotebookLM MCP、ダッシュボード ask は後続"
        >
          <input type="checkbox" checked={false} disabled />
          Google Drive／NotebookLM（Phase3・未実装）
        </label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          placeholder={
            isDigest
              ? "例: これは見送りで、〇〇だけタスクにしたい"
              : "コメント or 質問"
          }
          style={{ width: "100%", marginTop: 8 }}
        />
        <div className="card-triage-btns" style={{ marginTop: 6 }}>
          {isDigest ? (
            <button
              type="button"
              className="btn primary"
              disabled={pending || macPolling || !text.trim()}
              onClick={() => run("ask")}
            >
              {pending
                ? "返答中…"
                : engine === "cursor"
                  ? "送って Jarvis Cloud に聞く"
                  : "送って Gemini に聞く"}
            </button>
          ) : (
            <>
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
            </>
          )}
          {isDigest ? (
            <button
              type="button"
              className="btn"
              disabled={pending || !text.trim()}
              onClick={() => run("post")}
              title="返答なしでメモだけ残す"
            >
              メモのみ
            </button>
          ) : null}
        </div>

        <LocalHandoffBar
          localPrompt={handoffPrompt}
          notices={notices}
          forceOpen={needLocal}
          macPending={macPolling}
          onEnqueueMac={async (extraNote) => {
            const r = await enqueueCardCursorAsk(card.id, path, {
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
      </div>
      {err ? <p className="err">{err}</p> : null}
      {msg ? <p className="meta">{msg}</p> : null}
    </div>
  );
}
