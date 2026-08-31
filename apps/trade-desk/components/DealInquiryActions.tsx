"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { formatJstDateTime } from "@/lib/format";
import { BAIRITSU_MARKER } from "@/lib/reInquiryShared";
import type { InquiryChannel } from "@/lib/reInquiryChannel";
import { INQUIRY_CHANNEL_LABEL } from "@/lib/reInquiryChannel";
import { inquiryPhase } from "@/lib/rePipelineUi";
import { openInGoogleChrome } from "@/lib/openInChrome";

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

export default function DealInquiryActions({
  dealId,
  title,
  fromRaw: _fromRaw,
  inquiryStatus,
  messages,
  autoPassPendingRead,
  autoPassReason,
  lastSendJobFailed,
  onInquiryChanged,
}: {
  dealId: string;
  title: string;
  fromRaw?: string | null;
  inquiryStatus?: string | null;
  messages?: Msg[] | null;
  autoPassPendingRead?: boolean;
  autoPassReason?: string | null;
  lastSendJobFailed?: string | null;
  onInquiryChanged?: () => void;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<Step>("edit");
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);
  const [previewLoaded, setPreviewLoaded] = useState(false);
  const [landMethodBairitsu, setLandMethodBairitsu] = useState(false);
  const [channel, setChannel] = useState<InquiryChannel | null>(null);
  const [interestFormUrl, setInterestFormUrl] = useState<string | null>(null);
  const [listingUrl, setListingUrl] = useState<string | null>(null);
  const [statusOverride, setStatusOverride] = useState<string | null>(null);

  const status = statusOverride || inquiryStatus || "none";
  const canSend =
    status === "none" || status === "draft" || status === "";
  const showPack = !canSend || (messages || []).length > 0;
  const isHandoff = channel === "grok_handoff";
  const isKamiooyaForm = channel === "kamiooya_form";
  const isListingWeb = channel === "listing_web";

  useEffect(() => {
    setStatusOverride(null);
  }, [inquiryStatus]);

  const notifyChanged = useCallback(() => {
    onInquiryChanged?.();
    router.refresh();
  }, [onInquiryChanged, router]);

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
      if (data.inquiry_channel === "not_applicable") {
        setMsg("この案件は第一問合せ対象外です");
        setChannel("not_applicable");
        return;
      }
      if (data.inquiry_channel === "kamiooya_form") {
        setChannel("kamiooya_form");
        const url =
          typeof data.interest_form_url === "string"
            ? data.interest_form_url
            : typeof data.to === "string"
              ? data.to
              : "";
        setInterestFormUrl(url || null);
        setSubject(String(data.subject || ""));
        setBody(String(data.body || ""));
        setPreviewLoaded(true);
        return;
      }
      if (data.inquiry_channel === "listing_web") {
        setChannel("listing_web");
        const url =
          typeof data.listing_url === "string"
            ? data.listing_url
            : typeof data.to === "string"
              ? data.to
              : "";
        setListingUrl(url || null);
        setSubject(String(data.subject || ""));
        setBody(String(data.body || ""));
        setPreviewLoaded(true);
        return;
      }
      if (data.to) setTo(String(data.to));
      setSubject(String(data.subject || ""));
      setBody(String(data.body || ""));
      setLandMethodBairitsu(Boolean(data.land_method_bairitsu));
      if (
        data.inquiry_channel === "agent_email" ||
        data.inquiry_channel === "grok_handoff"
      ) {
        setChannel(data.inquiry_channel);
      }
      setPreviewLoaded(true);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "下書き取得エラー");
    }
  }, [dealId]);

  // 神大家フォーム経路を自動判定（メール編集 UI を出さないため）
  useEffect(() => {
    if (!canSend || previewLoaded || channel !== null) return;
    void loadPreview();
  }, [canSend, previewLoaded, channel, loadPreview]);

  const bairitsuMissing =
    landMethodBairitsu &&
    channel === "agent_email" &&
    !body.includes(BAIRITSU_MARKER);

  async function listingWebOneClick() {
    setBusy("listing_web");
    setMsg(null);
    try {
      const res = await fetch(`/api/re/deals/${dealId}/inquiry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "listing_web_submit" }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "失敗");
        return;
      }
      const text = String(data.body || "");
      const url = String(data.listing_url || listingUrl || "");
      try {
        if (text) await navigator.clipboard.writeText(text);
      } catch {
        /* clipboard may be denied — still open page */
      }
      let opened: "chrome" | "fallback" = "fallback";
      if (url) {
        opened = await openInGoogleChrome(url);
      }
      setStatusOverride(
        typeof data.inquiry_status === "string"
          ? data.inquiry_status
          : "awaiting_reply"
      );
      if (opened === "chrome") {
        setMsg(
          "定型文をコピーし、Google Chrome で掲載ページを開きました。貼って送信すれば完了です（判断履歴にも記録）"
        );
      } else {
        setMsg(
          "定型文をコピーしました。掲載は中央ブラウザで開いた可能性があります。ログインが必要なら Chrome で同じURLを開くか、KURASHIFT 自体を Chrome で開いて再実行してください（Mac では open-chrome ヘルパー導入可）"
        );
      }
      if (text) setBody(text);
      if (url) setListingUrl(url);
      notifyChanged();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(null);
    }
  }

  async function send() {
    if (!checked) {
      setMsg("確認チェックを入れてください");
      return;
    }
    if (!to.includes("@")) {
      setMsg("宛先メールを入力してください");
      return;
    }
    if (channel === "not_applicable") {
      setMsg("第一問合せ対象外です");
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
          inquiry_channel: channel || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "失敗");
      } else {
        const nextStatus =
          typeof data.inquiry_status === "string"
            ? data.inquiry_status
            : "sending";
        setStatusOverride(nextStatus);
        setMsg(
          nextStatus === "sending"
            ? "送信キューに入れました（問合せ：送信中）。Mac 常駐が送信します"
            : "キュー投入済み（Mac 常駐が送信します。失敗時はホームに表示されます）"
        );
        setOpen(false);
        setStep("edit");
        setChecked(false);
        setPreviewLoaded(false);
        notifyChanged();
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
        notifyChanged();
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
        notifyChanged();
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
        notifyChanged();
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
        問合せ: {inquiryPhase(status).label}
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
        {canSend && isListingWeb ? (
          <div style={{ width: "100%" }}>
            <button
              type="button"
              className="btn primary"
              style={{ fontSize: 12, padding: "6px 10px" }}
              disabled={busy !== null}
              onClick={() => void listingWebOneClick()}
            >
              {busy === "listing_web"
                ? "準備中…"
                : "掲載ページで問合せ（定型文コピー＋開く）"}
            </button>
            <p className="meta" style={{ marginTop: 4, lineHeight: 1.4 }}>
              1回で定型文をクリップボードへコピーし、掲載ページを開きます。貼り付けて送信したら、こちらは問合せ済になります。
            </p>
            {body ? (
              <pre
                style={{
                  marginTop: 6,
                  padding: 8,
                  fontSize: 11,
                  whiteSpace: "pre-wrap",
                  background: "var(--panel, #f8fafc)",
                  border: "1px solid var(--border, #e2e8f0)",
                  borderRadius: 6,
                  maxHeight: 160,
                  overflow: "auto",
                }}
              >
                {body}
              </pre>
            ) : null}
          </div>
        ) : null}
        {canSend && channel !== "not_applicable" && !isKamiooyaForm && !isListingWeb ? (
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
            {isHandoff ? "詳細編集してGrok依頼" : "詳細編集して問合せ"}
          </button>
        ) : null}
        {canSend && !isListingWeb ? (
          <button
            type="button"
            className="btn"
            style={{ fontSize: 12, padding: "4px 8px" }}
            disabled={busy !== null}
            onClick={async () => {
              if (!previewLoaded || channel === null) {
                await loadPreview();
              }
            }}
          >
            経路を確認
          </button>
        ) : null}
        {canSend && (isKamiooyaForm || interestFormUrl) ? (
          <>
            {interestFormUrl ? (
              <a
                className="btn primary"
                href={interestFormUrl}
                target="_blank"
                rel="noreferrer"
                style={{ fontSize: 12, padding: "4px 8px" }}
              >
                紹介フォームを開く
              </a>
            ) : null}
            <button
              type="button"
              className="btn"
              style={{ fontSize: 12, padding: "4px 8px" }}
              disabled={busy !== null}
              onClick={async () => {
                setBusy("kamiooya_form");
                setMsg(null);
                try {
                  const res = await fetch(`/api/re/deals/${dealId}/inquiry`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ action: "kamiooya_form_submitted" }),
                  });
                  const data = await res.json();
                  if (!res.ok) {
                    setMsg(data.error || "失敗");
                  } else {
                    setMsg("フォーム送信済として記録（運営返信待ち）");
                    setStatusOverride("awaiting_reply");
                    notifyChanged();
                  }
                } catch (e) {
                  setMsg(e instanceof Error ? e.message : "エラー");
                } finally {
                  setBusy(null);
                }
              }}
            >
              {busy === "kamiooya_form" ? "…" : "フォーム送信した"}
            </button>
          </>
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
              {channel ? (
                <p className="meta" style={{ marginBottom: 6 }}>
                  経路: {INQUIRY_CHANNEL_LABEL[channel]}
                </p>
              ) : null}
              {isHandoff ? (
                <p className="meta" style={{ color: "#4338ca", marginBottom: 6 }}>
                  仲介メールなし → 自分宛に依頼（Grok が拾う）
                </p>
              ) : null}
              {landMethodBairitsu && channel === "agent_email" ? (
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
                  type="email"
                  value={to}
                  onChange={(e) => setTo(e.target.value)}
                  readOnly={isHandoff}
                  style={{
                    display: "block",
                    width: "100%",
                    marginTop: 2,
                    background: isHandoff ? "#f1f5f9" : undefined,
                  }}
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
              {formatJstDateTime(m.occurred_at)} {m.direction}/{m.kind}:{" "}
              {(m.subject || "").slice(0, 28)}
            </li>
          ))}
        </ul>
      ) : null}
      {msg ? <div className="meta" style={{ marginTop: 4 }}>{msg}</div> : null}
    </div>
  );
}
