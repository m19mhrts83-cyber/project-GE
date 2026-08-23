"use client";

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { BAIRITSU_MARKER } from "@/lib/reInquiryShared";

type Msg = {
  direction?: string;
  kind?: string;
  subject?: string;
  from_email?: string;
  occurred_at?: string;
  body_text?: string;
};

type Step = "edit" | "confirm";

async function sha256Hex(text: string): Promise<string> {
  const data = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function parseEmail(fromRaw: string | undefined): string {
  if (!fromRaw) return "";
  const m = fromRaw.match(/<([^>]+)>/);
  return (m ? m[1] : fromRaw).trim();
}

export default function DealInquiryActions({
  dealId,
  title,
  fromRaw,
  inquiryStatus,
  messages,
  autoPassPendingRead,
  autoPassReason,
  lastSendJobFailed,
}: {
  dealId: string;
  title: string;
  fromRaw?: string | null;
  inquiryStatus?: string | null;
  messages?: Msg[] | null;
  autoPassPendingRead?: boolean;
  autoPassReason?: string | null;
  lastSendJobFailed?: string | null;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<Step>("edit");
  const [to, setTo] = useState(() => parseEmail(fromRaw || undefined));
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);
  const [previewLoaded, setPreviewLoaded] = useState(false);
  const [landMethodBairitsu, setLandMethodBairitsu] = useState(false);

  const status = inquiryStatus || "none";
  const canSend =
    status === "none" || status === "draft" || status === "";
  const showPack = !canSend || (messages || []).length > 0;

  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");

  const loadPreview = useCallback(async () => {
    setMsg(null);
    try {
      const res = await fetch(`/api/re/deals/${dealId}/inquiry-preview`);
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "下書き取得失敗");
        return;
      }
      if (data.to) setTo(String(data.to));
      setSubject(String(data.subject || ""));
      setBody(String(data.body || ""));
      setLandMethodBairitsu(Boolean(data.land_method_bairitsu));
      setPreviewLoaded(true);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "下書き取得エラー");
    }
  }, [dealId]);

  const bairitsuMissing =
    landMethodBairitsu && !body.includes(BAIRITSU_MARKER);

  async function send() {
    if (!checked) {
      setMsg("確認チェックを入れてください");
      return;
    }
    if (!to.includes("@")) {
      setMsg("宛先メールを入力してください");
      return;
    }
    if (bairitsuMissing) {
      setMsg("倍率地域のため固定資産税依頼文が必要です（編集画面に戻って追記）");
      return;
    }
    setBusy("send");
    setMsg(null);
    try {
      const body_sha256 = await sha256Hex(body);
      const res = await fetch(`/api/re/deals/${dealId}/inquiry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "send",
          to,
          subject,
          body,
          ui_confirmed: true,
          confirm_snapshot: { to, subject, body_sha256 },
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "失敗");
      } else {
        setMsg(
          "キュー投入済み（Mac 常駐が送信します。失敗時はホームに表示されます）"
        );
        setOpen(false);
        setStep("edit");
        setChecked(false);
        router.refresh();
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(null);
    }
  }

  async function pack() {
    setBusy("pack");
    setMsg(null);
    try {
      const res = await fetch(`/api/re/deals/${dealId}/inquiry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "build_ops_pack" }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "失敗");
      } else {
        setMsg(
          data.consultation_id
            ? `運営相談パック作成 → /consultations/${data.consultation_id}`
            : "パックをキューしました"
        );
        router.refresh();
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(null);
    }
  }

  async function formDraft() {
    setBusy("form_draft");
    setMsg(null);
    try {
      const res = await fetch(`/api/re/deals/${dealId}/inquiry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "form_draft" }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "失敗");
      } else {
        setMsg(
          "フォーム下書きをキューしました（Mac 常駐実行後、ドロワーに反映）"
        );
        router.refresh();
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(null);
    }
  }

  const showFormDraft =
    status === "has_reply" || status === "awaiting_reply" || showPack;

  async function autopass(action: "autopass_confirm" | "autopass_reject") {
    setBusy(action);
    setMsg(null);
    try {
      const res = await fetch(`/api/re/deals/${dealId}/inquiry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "失敗");
      } else {
        setMsg(
          action === "autopass_confirm"
            ? "既読で正しい → 既読ジョブをキュー"
            : "誤り → 候補（info）に戻しました"
        );
        router.refresh();
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div style={{ minWidth: 160 }}>
      <div className="meta" style={{ marginBottom: 4 }}>
        問合せ: {status}
      </div>
      {lastSendJobFailed ? (
        <div className="meta" style={{ marginBottom: 4, color: "#b00020" }}>
          送信失敗: {lastSendJobFailed.slice(0, 80)}
        </div>
      ) : null}
      {autoPassPendingRead ? (
        <div style={{ marginBottom: 6 }}>
          <div className="meta">自動見送り・未既読（{autoPassReason || "—"}）</div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn"
              style={{ fontSize: 11, padding: "2px 6px" }}
              disabled={busy !== null}
              onClick={() => autopass("autopass_confirm")}
            >
              既読で正しい
            </button>
            <button
              type="button"
              className="btn"
              style={{ fontSize: 11, padding: "2px 6px" }}
              disabled={busy !== null}
              onClick={() => autopass("autopass_reject")}
            >
              誤り（候補へ）
            </button>
          </div>
        </div>
      ) : null}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 4 }}>
        {canSend ? (
          <button
            type="button"
            className="btn primary"
            style={{ fontSize: 12, padding: "4px 8px" }}
            disabled={busy !== null}
            onClick={async () => {
              const next = !open;
              setOpen(next);
              setStep("edit");
              setChecked(false);
              if (next && !previewLoaded) {
                await loadPreview();
              }
            }}
          >
            詳細編集して問合せ
          </button>
        ) : null}
        {showPack ? (
          <button
            type="button"
            className="btn"
            style={{ fontSize: 12, padding: "4px 8px" }}
            disabled={busy !== null}
            onClick={pack}
          >
            {busy === "pack" ? "…" : "運営相談パック"}
          </button>
        ) : null}
        {showFormDraft ? (
          <button
            type="button"
            className="btn"
            style={{ fontSize: 12, padding: "4px 8px" }}
            disabled={busy !== null}
            onClick={formDraft}
          >
            {busy === "form_draft" ? "…" : "フォーム下書き"}
          </button>
        ) : null}
      </div>
      {open && canSend ? (
        <div
          style={{
            marginTop: 8,
            padding: 8,
            border: "1px solid var(--border, #ccc)",
            borderRadius: 6,
            maxWidth: 360,
          }}
        >
          {step === "edit" ? (
            <>
              {landMethodBairitsu ? (
                <p className="meta" style={{ color: "#b45309", marginBottom: 6 }}>
                  倍率地域 — 固定資産税（課税明細）の依頼を本文に含めます
                </p>
              ) : null}
              {bairitsuMissing ? (
                <p className="meta" style={{ color: "#b00020", marginBottom: 6 }}>
                  【倍率地域のため】の固定資産税依頼が欠けています
                </p>
              ) : null}
              <label className="meta">
                To
                <input
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                  style={{ display: "block", width: "100%", marginTop: 2 }}
                />
              </label>
              <label className="meta" style={{ display: "block", marginTop: 6 }}>
                件名
                <input
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  style={{ display: "block", width: "100%", marginTop: 2 }}
                />
              </label>
              <label className="meta" style={{ display: "block", marginTop: 6 }}>
                本文
                <textarea
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  rows={8}
                  style={{ display: "block", width: "100%", marginTop: 2 }}
                />
              </label>
              <p className="meta" style={{ marginTop: 6 }}>
                From: matsuno.estate@gmail.com
              </p>
              <button
                type="button"
                className="btn primary"
                disabled={busy !== null}
                onClick={() => {
                  setStep("confirm");
                  setChecked(false);
                }}
                style={{ marginTop: 6 }}
              >
                確認画面へ
              </button>
            </>
          ) : (
            <>
              <p className="meta">
                <strong>送信内容の再確認</strong>（編集不可）
              </p>
              <p className="meta" style={{ marginTop: 6 }}>
                From: matsuno.estate@gmail.com
              </p>
              <p className="meta">
                <strong>To:</strong> {to}
              </p>
              <p className="meta">
                <strong>件名:</strong> {subject}
              </p>
              <pre
                className="meta"
                style={{
                  whiteSpace: "pre-wrap",
                  maxHeight: 120,
                  overflow: "auto",
                  marginTop: 6,
                }}
              >
                {body.slice(0, 600)}
                {body.length > 600 ? "…" : ""}
              </pre>
              <label className="meta" style={{ display: "flex", gap: 6, marginTop: 8 }}>
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(e) => setChecked(e.target.checked)}
                />
                宛先・件名・本文を確認した
              </label>
              <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
                <button
                  type="button"
                  className="btn"
                  disabled={busy !== null}
                  onClick={() => setStep("edit")}
                >
                  戻る
                </button>
                <button
                  type="button"
                  className="btn primary"
                  disabled={busy !== null || !checked}
                  onClick={send}
                >
                  {busy === "send" ? "送信中…" : "確認したので送信キューへ"}
                </button>
              </div>
            </>
          )}
        </div>
      ) : null}
      {(messages || []).length > 0 ? (
        <ul className="meta" style={{ paddingLeft: 14, marginTop: 6 }}>
          {(messages || []).slice(-3).map((m, i) => (
            <li key={i}>
              {(m.occurred_at || "").slice(0, 10)} {m.direction}/{m.kind}:{" "}
              {(m.subject || "").slice(0, 28)}
            </li>
          ))}
        </ul>
      ) : null}
      {msg ? <div className="meta" style={{ marginTop: 4 }}>{msg}</div> : null}
    </div>
  );
}
