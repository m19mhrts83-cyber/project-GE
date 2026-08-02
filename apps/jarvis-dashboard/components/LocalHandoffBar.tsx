"use client";

import { useState, useTransition } from "react";

type Props = {
  localPrompt: string;
  notices?: string[];
  forceOpen?: boolean;
  onEnqueueMac?: (extraNote: string) => Promise<{
    ok: boolean;
    error?: string;
    message?: string;
  }>;
  macPending?: boolean;
};

export default function LocalHandoffBar({
  localPrompt,
  notices = [],
  forceOpen = false,
  onEnqueueMac,
  macPending = false,
}: Props) {
  const [open, setOpen] = useState(forceOpen);
  const [extra, setExtra] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [pending, start] = useTransition();

  const show = open || forceOpen || notices.length > 0;

  async function copyPrompt() {
    setErr(null);
    const block = [
      localPrompt,
      extra.trim()
        ? `\nユーザー追記（不満・Macでやってほしいこと）:\n${extra.trim()}`
        : "",
    ]
      .filter(Boolean)
      .join("\n");
    try {
      await navigator.clipboard.writeText(block);
      setMsg("ローカル Cursor 用テキストをコピーしました（Mac の Cursor に貼ってください）");
    } catch {
      setErr("コピーに失敗しました。下のテキストを手動選択してコピーしてください。");
      setOpen(true);
    }
  }

  if (!show && !localPrompt) return null;

  return (
    <div className={`local-handoff${forceOpen ? " is-forced" : ""}`}>
      {notices.length > 0 ? (
        <ul className="fallback-notices" aria-live="polite">
          {notices.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}

      <div className="local-handoff-head">
        <p className="local-handoff-title">この続きはローカルで</p>
        {!forceOpen ? (
          <button
            type="button"
            className="btn"
            style={{ fontSize: "0.8rem", padding: "2px 8px" }}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? "閉じる" : "開く"}
          </button>
        ) : null}
      </div>

      {(open || forceOpen) && (
        <>
          <p className="meta" style={{ margin: "0 0 8px" }}>
            文脈ごと引き継ぎます。コピーして Mac の Cursor
            に貼るか、Mac ワーカーに依頼できます。
          </p>
          <label className="promote-label">
            追記（任意・不満点や Mac でやってほしいこと）
            <textarea
              value={extra}
              onChange={(e) => setExtra(e.target.value)}
              rows={2}
              disabled={pending || macPending}
            />
          </label>
          <div className="card-triage-btns" style={{ marginTop: 8 }}>
            <button
              type="button"
              className="btn primary"
              disabled={pending || macPending || !localPrompt}
              onClick={() => void copyPrompt()}
            >
              ローカル用にコピー
            </button>
            {onEnqueueMac ? (
              <button
                type="button"
                className="btn"
                disabled={pending || macPending || !localPrompt}
                onClick={() => {
                  setErr(null);
                  setMsg(null);
                  start(async () => {
                    const r = await onEnqueueMac(extra);
                    if (!r.ok) {
                      setErr(r.error || "Mac 依頼に失敗しました");
                      return;
                    }
                    setMsg(r.message || "Mac に依頼しました");
                  });
                }}
              >
                {macPending ? "Mac 処理中…" : "Mac Cursor に依頼"}
              </button>
            ) : null}
          </div>
          {err ? (
            <textarea
              className="local-handoff-fallback-text"
              readOnly
              rows={6}
              value={[
                localPrompt,
                extra.trim()
                  ? `\nユーザー追記:\n${extra.trim()}`
                  : "",
              ]
                .filter(Boolean)
                .join("\n")}
            />
          ) : null}
        </>
      )}
      {err ? <p className="err">{err}</p> : null}
      {msg ? <p className="meta">{msg}</p> : null}
    </div>
  );
}
