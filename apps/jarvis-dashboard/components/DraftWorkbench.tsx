"use client";

import { useEffect, useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import {
  getCursorReviseStatus,
  reviseTriageDraft,
  saveTriageDraft,
  sendTriageAfterConfirm,
  type CursorReviseState,
  type ReviseEngine,
} from "@/app/actions/triage";
import { researchWithTavily } from "@/app/actions/tavilyResearch";

type Payload = {
  draft_gemini?: string;
  draft_cursor?: string;
  yoritoori_appended?: boolean;
  sent_at?: string;
  cursor_revise?: CursorReviseState;
};

type Props = {
  id: string;
  path: string;
  subject: string | null;
  toEmail: string | null;
  partner?: string | null;
  folder?: string | null;
  /** partner のとき OneDrive やり取りの位置づけを表示 */
  lane?: string | null;
  draftText: string | null;
  payload: Payload | null | unknown;
  status: string;
  gmailReady: boolean;
  resolvedTo?: string;
  toSource?: string;
};

type Tab = "edit" | "gemini" | "cursor";

function readCursorRevise(payload: Payload | null | unknown): CursorReviseState | null {
  const pl = (payload && typeof payload === "object" ? payload : {}) as Payload;
  const cr = pl.cursor_revise;
  if (!cr || typeof cr !== "object") return null;
  return cr;
}

export default function DraftWorkbench({
  id,
  path,
  subject,
  toEmail,
  partner,
  folder,
  lane,
  draftText,
  payload,
  status,
  gmailReady,
  resolvedTo,
  toSource,
}: Props) {
  const router = useRouter();
  const pl = (payload && typeof payload === "object" ? payload : {}) as Payload;
  const gemini = (pl.draft_gemini || "").trim();
  const cursor = (pl.draft_cursor || "").trim();

  const initialTo = (resolvedTo || toEmail || "").trim();
  const [tab, setTab] = useState<Tab>("edit");
  const [draft, setDraft] = useState(draftText || "");
  const [to, setTo] = useState(initialTo);
  const [instruction, setInstruction] = useState("");
  const [engine, setEngine] = useState<ReviseEngine>("cursor");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pending, start] = useTransition();
  const [tavilyQ, setTavilyQ] = useState(() =>
    [subject, partner].filter(Boolean).join(" ").trim().slice(0, 120),
  );
  const [polling, setPolling] = useState(() => {
    const cr = readCursorRevise(payload);
    return cr?.status === "queued" || cr?.status === "running";
  });

  const previewSubject = useMemo(() => {
    const s = (subject || "").trim() || "（件名なし）";
    return /^re:/i.test(s) ? s : `Re: ${s}`;
  }, [subject]);

  useEffect(() => {
    if (!polling) return;
    let cancelled = false;
    let ticks = 0;
    const tick = async () => {
      ticks += 1;
      const r = await getCursorReviseStatus(id);
      if (cancelled) return;
      if (!r.ok) {
        setErr(r.error);
        return;
      }
      const st = r.revise?.status;
      if (st === "done") {
        if (r.draft) setDraft(r.draft);
        setMsg("Jarvis Cloud／Mac で見直し完了");
        setErr(null);
        setPolling(false);
        setTab("cursor");
        router.refresh();
        return;
      }
      if (st === "error") {
        setErr(r.revise?.error || "Jarvis Cloud 見直しに失敗しました");
        setPolling(false);
        router.refresh();
        return;
      }
      if (ticks >= 80) {
        setErr(
          "見直しがタイムアウトしました。Mac が起動中か、launchd ワーカーを確認してください。",
        );
        setPolling(false);
        return;
      }
      if (st === "queued" || st === "running") {
        const via =
          r.revise?.via === "mac_fallback"
            ? "（Jarvis Cloud 不可のためローカル Mac へ移行）"
            : "";
        setMsg(
          st === "running"
            ? `見直し中…${via}`
            : `Mac キュー待ち…${via}`,
        );
      }
    };
    void tick();
    const t = setInterval(() => {
      void tick();
    }, 2500);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [polling, id, router]);

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
      `To: ${to || toEmail || "（未設定）"}`,
      `Subject: ${previewSubject}`,
      partner ? `partner: ${partner}` : "",
      folder ? `folder: ${folder}` : "",
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
      <aside className="draft-positioning" aria-label="下書きの位置づけ">
        {lane === "partner" ? (
          <>
            <p className="draft-positioning-title">パートナー返信の位置づけ</p>
            <ul>
              <li>
                <strong>初稿</strong>
                … OneDrive の <code>5.やり取り.md</code>{" "}
                直近を踏まえて夜間トリアージが作成
              </li>
              <li>
                <strong>見直し</strong>
                … いまの下書き＋下の指示のみ。やり取り MD
                は再読しません
              </li>
              <li>
                <strong>経緯を足すとき</strong>
                … 指示に要点を書くか、下書きを手で追記
              </li>
            </ul>
          </>
        ) : (
          <>
            <p className="draft-positioning-title">返信下書きの位置づけ</p>
            <ul>
              <li>
                <strong>初稿</strong>
                … 受信メール／スレッド文脈から作成
              </li>
              <li>
                <strong>見直し</strong>
                … いまの下書き＋下の指示のみ（元メールは再読しません）
              </li>
            </ul>
          </>
        )}
      </aside>

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
        宛先 To
        <input
          className="draft-instruction"
          value={to}
          onChange={(e) => setTo(e.target.value)}
          placeholder="例: suzuki@homeplanner.co.jp"
        />
      </label>
      {!initialTo ? (
        <p className="draft-err">
          宛先が未設定でした。連絡先から補完できない場合は手入力するか、チャットで送付先を指定してください。
        </p>
      ) : toSource === "contacts" ? (
        <p className="draft-hint">宛先は連絡先一覧から補完（{partner || folder || "—"}）</p>
      ) : null}

      <label className="draft-instruction-label">
        見直し指示（任意）
        <input
          className="draft-instruction"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder={
            lane === "partner"
              ? "例: もう少し短く／署名依頼の件も一文入れて"
              : "例: もう少し短く、丁寧に"
          }
        />
      </label>
      <div className="tavily-row">
        <label className="draft-instruction-label" style={{ flex: 1 }}>
          Web下調べ（Tavily・送信しない）
          <input
            className="draft-instruction"
            value={tavilyQ}
            onChange={(e) => setTavilyQ(e.target.value)}
            placeholder="検索語（件名・トピック）"
            disabled={pending || polling}
          />
        </label>
        <div className="tavily-actions">
          <button
            type="button"
            className="btn"
            disabled={pending || polling || !tavilyQ.trim()}
            onClick={() =>
              start(async () => {
                setErr(null);
                const r = await researchWithTavily(tavilyQ);
                if (!r.ok) {
                  setErr(r.error);
                  return;
                }
                setInstruction((prev) =>
                  prev.trim()
                    ? `${prev.trim()}\n\n${r.block}`
                    : `下調べを踏まえて丁寧に整えて。\n\n${r.block}`,
                );
                setMsg("Tavily の結果を見直し指示に追記しました（未送信）");
              })
            }
          >
            指示へ
          </button>
          <button
            type="button"
            className="btn"
            disabled={pending || polling || !tavilyQ.trim()}
            onClick={() =>
              start(async () => {
                setErr(null);
                const r = await researchWithTavily(tavilyQ);
                if (!r.ok) {
                  setErr(r.error);
                  return;
                }
                const quote = `\n\n---\n${r.block}\n---\n`;
                setDraft((prev) => `${prev.trimEnd()}${quote}`);
                setTab("edit");
                setMsg("Tavily の結果を下書き末尾に引用しました（未送信）");
              })
            }
          >
            下書き末尾へ
          </button>
        </div>
      </div>
      <p className="draft-hint">
        「見直しを実行」は、上の下書きとこの指示だけを見ます（{lane === "partner"
          ? "やり取り.md は開き直さない"
          : "元メール全文は再読しない"}
        ）。Tavily は文脈注入のみで、送信確認ゲートは変わりません。
      </p>

      <fieldset className="draft-engine">
        <legend>見直しエンジン</legend>
        <label className="draft-engine-opt">
          <input
            type="radio"
            name={`revise-engine-${id}`}
            checked={engine === "cursor"}
            onChange={() => setEngine("cursor")}
            disabled={pending || polling}
          />
          Jarvis Cloud
        </label>
        <label className="draft-engine-opt">
          <input
            type="radio"
            name={`revise-engine-${id}`}
            checked={engine === "gemini"}
            onChange={() => setEngine("gemini")}
            disabled={pending || polling}
          />
          Gemini
        </label>
      </fieldset>
      {engine === "cursor" ? (
        <p className="draft-hint">
          Jarvis Cloud（Cursor Cloud Agent）が本線です。失敗・未キー・タイムアウト時は
          Mac ワーカーへ自動フォールバックし、その旨を表示します。
        </p>
      ) : null}

      <div className="draft-toolbar">
        <button
          type="button"
          className="btn"
          disabled={pending || polling}
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
          className="btn primary"
          disabled={pending || polling || !draft.trim()}
          onClick={() =>
            start(async () => {
              setErr(null);
              const r = await reviseTriageDraft(
                id,
                instruction,
                draft,
                path,
                engine,
              );
              if (!r.ok) {
                setErr(r.error);
                return;
              }
              if (engine === "cursor" && r.queued) {
                setMsg(r.message || "Jarvis Cloud／Mac にキューしました");
                setPolling(true);
                router.refresh();
                return;
              }
              if (r.draft) setDraft(r.draft);
              setMsg(r.message || "見直し完了");
              router.refresh();
            })
          }
        >
          {polling
            ? "見直し中…"
            : engine === "cursor"
              ? "Jarvis Cloudで見直し"
              : "Geminiで見直し"}
        </button>
        <button type="button" className="btn" onClick={localCursorCopy}>
          ローカルCursor用コピー
        </button>
        {status === "pending" ? (
          <button
            type="button"
            id="draft-send-open"
            className="btn primary"
            disabled={pending || polling || !draft.trim() || !to.trim()}
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
              <strong>To:</strong> {to || "（未設定）"}
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
                disabled={pending || !to.trim()}
                onClick={() =>
                  start(async () => {
                    setErr(null);
                    // 手入力 To を先に下書き保存メタへ（from_email 更新は send 側でも実施）
                    await saveTriageDraft(id, draft, path);
                    const r = await sendTriageAfterConfirm(
                      id,
                      draft,
                      path,
                      true,
                      to.trim(),
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
