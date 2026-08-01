"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import {
  reviseTriageDraftWithGemini,
  saveTriageDraft,
  sendTriageAfterConfirm,
} from "@/app/actions/triage";

type Payload = {
  draft_gemini?: string;
  draft_cursor?: string;
  yoritoori_appended?: boolean;
  sent_at?: string;
};

type Props = {
  id: string;
  path: string;
  subject: string | null;
  toEmail: string | null;
  draftText: string | null;
  payload: Payload | null | unknown;
  status: string;
  gmailReady: boolean;
};

type Tab = "edit" | "gemini" | "cursor";

export default function DraftWorkbench({
  id,
  path,
  subject,
  toEmail,
  draftText,
  payload,
  status,
  gmailReady,
}: Props) {
  const router = useRouter();
  const pl = (payload && typeof payload === "object" ? payload : {}) as Payload;
  const gemini = (pl.draft_gemini || "").trim();
  const cursor = (pl.draft_cursor || "").trim();

  const [tab, setTab] = useState<Tab>("edit");
  const [draft, setDraft] = useState(draftText || "");
  const [instruction, setInstruction] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pending, start] = useTransition();

  const previewSubject = useMemo(() => {
    const s = (subject || "").trim() || "（件名なし）";
    return /^re:/i.test(s) ? s : `Re: ${s}`;
  }, [subject]);

  function applyTab(t: Tab) {
    setTab(t);
    if (t === "gemini" && gemini) setDraft(gemini);
    if (t === "cursor" && cursor) setDraft(cursor);
    if (t === "edit" && draftText) setDraft(draftText);
  }

  function localCursorCopy() {
    const block = [
      "【ローカル Cursor 用】パートナー返信の見直し",
      `id: ${id}`,
      `To: ${toEmail || "（未設定）"}`,
      `Subject: ${previewSubject}`,
      instruction.trim() ? `見直し指示: ${instruction.trim()}` : "",
      "----- 下書き -----",
      draft,
      "-----",
      "確認後: yoritoori_send.py またはダッシュボードから送信",
    ]
      .filter(Boolean)
      .join("\n");
    void navigator.clipboard.writeText(block);
    setMsg("ローカル Cursor 用テキストをコピーしました");
    setErr(null);
  }

  return (
    <div className="draft-workbench">
      <div className="draft-tabs">
        <button
          type="button"
          className={tab === "edit" ? "draft-tab on" : "draft-tab"}
          onClick={() => applyTab("edit")}
        >
          編集中
        </button>
        {gemini ? (
          <button
            type="button"
            className={tab === "gemini" ? "draft-tab on" : "draft-tab"}
            onClick={() => applyTab("gemini")}
          >
            Gemini案
          </button>
        ) : null}
        {cursor ? (
          <button
            type="button"
            className={tab === "cursor" ? "draft-tab on" : "draft-tab"}
            onClick={() => applyTab("cursor")}
          >
            Cursor案
          </button>
        ) : null}
      </div>

      <textarea
        className="draft-textarea"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        rows={12}
        placeholder="返信下書き"
      />

      <label className="draft-instruction-label">
        見直し指示（任意）
        <input
          className="draft-instruction"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="例: もう少し短く、丁寧に"
        />
      </label>

      <div className="draft-toolbar">
        <button
          type="button"
          className="btn"
          disabled={pending}
          onClick={() =>
            start(async () => {
              setErr(null);
              const r = await saveTriageDraft(id, draft, path);
              if (!r.ok) setErr(r.error);
              else {
                setMsg("下書きを保存しました");
                router.refresh();
              }
            })
          }
        >
          下書き保存
        </button>
        <button
          type="button"
          className="btn"
          disabled={pending}
          onClick={() =>
            start(async () => {
              setErr(null);
              const r = await reviseTriageDraftWithGemini(
                id,
                instruction,
                draft,
                path,
              );
              if (!r.ok) setErr(r.error);
              else {
                if (r.draft) setDraft(r.draft);
                setMsg(r.message || "見直し完了");
                router.refresh();
              }
            })
          }
        >
          Geminiで見直し
        </button>
        <button type="button" className="btn" onClick={localCursorCopy}>
          ローカルCursor用コピー
        </button>
        {status === "pending" ? (
          <button
            type="button"
            className="btn primary"
            disabled={pending || !draft.trim()}
            onClick={() => {
              setConfirmOpen(true);
              setErr(null);
            }}
          >
            送信…
          </button>
        ) : null}
      </div>

      {!gmailReady && status === "pending" ? (
        <p className="draft-hint">
          サーバー送信シークレット未設定のため、送信ボタンは失敗する場合があります。そのときはローカル
          Cursor / yoritoori_send を使ってください。
        </p>
      ) : null}

      {msg ? <p className="draft-ok">{msg}</p> : null}
      {err ? <p className="draft-err">{err}</p> : null}

      {confirmOpen ? (
        <div className="send-confirm-backdrop" role="dialog" aria-modal>
          <div className="send-confirm">
            <h3>送信確認</h3>
            <p className="meta">まだ送っていません。内容を確認してください。</p>
            <p>
              <strong>To:</strong> {toEmail || "（未設定）"}
            </p>
            <p>
              <strong>Subject:</strong> {previewSubject}
            </p>
            <pre className="draft-body">{draft}</pre>
            <div className="draft-toolbar">
              <button
                type="button"
                className="btn"
                onClick={() => setConfirmOpen(false)}
              >
                戻る
              </button>
              <button
                type="button"
                className="btn primary"
                disabled={pending || !toEmail}
                onClick={() =>
                  start(async () => {
                    setErr(null);
                    const r = await sendTriageAfterConfirm(
                      id,
                      draft,
                      path,
                      true,
                    );
                    if (!r.ok) {
                      setErr(r.error);
                      return;
                    }
                    setConfirmOpen(false);
                    setMsg(r.message || "送信しました");
                    router.refresh();
                  })
                }
              >
                これで送っていいです
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
