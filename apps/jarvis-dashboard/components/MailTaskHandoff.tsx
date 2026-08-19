"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import {
  enqueueMailCursorAsk,
  getMailCursorAskStatus,
  launchMailCloudTask,
  type MailTaskState,
} from "@/app/actions/triage";
import LocalHandoffBar from "@/components/LocalHandoffBar";
import type { CursorAskState } from "@/lib/localHandoff";

type Payload = {
  cursor_ask?: CursorAskState;
  mail_task?: MailTaskState;
  body_ja?: string;
};

export default function MailTaskHandoff({
  id,
  path,
  payload,
}: {
  id: string;
  path: string;
  payload: unknown;
}) {
  const router = useRouter();
  const pl = (payload && typeof payload === "object" ? payload : {}) as Payload;
  const [instruction, setInstruction] = useState(
    "このメールの指示どおり、返信以外の作業を進めてください。",
  );
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [url, setUrl] = useState(pl.mail_task?.url || "");
  const [localPrompt, setLocalPrompt] = useState("");
  const [pending, start] = useTransition();
  const [macPolling, setMacPolling] = useState(
    pl.cursor_ask?.status === "queued" || pl.cursor_ask?.status === "running",
  );
  const [reply, setReply] = useState(pl.cursor_ask?.reply || "");

  useEffect(() => {
    if (!macPolling) return;
    let cancelled = false;
    let ticks = 0;
    const tick = async () => {
      ticks += 1;
      const r = await getMailCursorAskStatus(id);
      if (cancelled) return;
      if (!r.ok) {
        setErr(r.error);
        return;
      }
      const st = r.ask?.status;
      if (st === "done") {
        setReply(r.ask?.reply || "");
        setMsg("Mac ワーカーが完了しました");
        setMacPolling(false);
        router.refresh();
        return;
      }
      if (st === "error") {
        setErr(r.ask?.error || "Mac ワーカーが失敗しました");
        setMacPolling(false);
        return;
      }
      if (ticks >= 80) {
        setMacPolling(false);
        setErr("Mac の応答待ちが長くなっています。起動中か確認してください。");
        return;
      }
      setTimeout(() => void tick(), 4000);
    };
    void tick();
    return () => {
      cancelled = true;
    };
  }, [id, macPolling, router]);

  return (
    <section className="mail-task-handoff">
      <h2 style={{ fontSize: "1rem", marginTop: 20 }}>返信以外の次の一手</h2>
      <p className="meta">
        メール返信ではなく、指示の作業を Cloud Agent か Mac の Cursor
        に渡せます。送信はしません。
      </p>
      <label className="draft-instruction-label">
        作業指示
        <textarea
          className="draft-instruction"
          rows={3}
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          disabled={pending || macPolling}
        />
      </label>
      <div className="draft-toolbar">
        <button
          type="button"
          className="btn primary"
          disabled={pending || macPolling || !instruction.trim()}
          onClick={() =>
            start(async () => {
              setErr(null);
              const r = await launchMailCloudTask(id, instruction, path);
              if (!r.ok) {
                setErr(r.error);
                if (r.localPrompt) setLocalPrompt(r.localPrompt);
                return;
              }
              setUrl(r.url || "");
              setLocalPrompt(r.localPrompt || "");
              setMsg(r.message || "Cloud Agent を起動しました");
              router.refresh();
            })
          }
        >
          {pending ? "起動中…" : "Cloud Agent に頼む"}
        </button>
        <button
          type="button"
          className="btn"
          disabled={pending || macPolling || !instruction.trim()}
          onClick={() =>
            start(async () => {
              setErr(null);
              const r = await enqueueMailCursorAsk(id, instruction, path);
              if (!r.ok) {
                setErr(r.error);
                if (r.localPrompt) setLocalPrompt(r.localPrompt);
                return;
              }
              setLocalPrompt(r.localPrompt || "");
              setMsg(r.message || "Mac に依頼しました");
              setMacPolling(true);
              router.refresh();
            })
          }
        >
          {macPolling ? "Mac 処理中…" : "Mac ワーカーに渡す"}
        </button>
      </div>
      {url ? (
        <p className="draft-ok">
          Cloud:{" "}
          <a href={url} target="_blank" rel="noreferrer">
            エージェントを開く
          </a>
        </p>
      ) : null}
      {reply ? <pre className="orig-body">{reply}</pre> : null}
      {msg ? <p className="draft-ok">{msg}</p> : null}
      {err ? <p className="draft-err">{err}</p> : null}
      <LocalHandoffBar
        localPrompt={localPrompt}
        forceOpen={Boolean(localPrompt) && !url && !macPolling}
      />
    </section>
  );
}
