"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { BAIRITSU_MARKER } from "@/lib/reInquiryShared";
import type { InquiryChannel } from "@/lib/reInquiryChannel";
import { INQUIRY_CHANNEL_LABEL } from "@/lib/reInquiryChannel";

async function sha256Hex(text: string): Promise<string> {
  const data = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export default function DealInquiryQuickButton({
  dealId,
  title,
  fromRaw: _fromRaw,
  canQuickSend,
  hasTo,
  inquiryChannel: inquiryChannelProp,
  badges,
  compact,
  openHref,
  onSent,
}: {
  dealId: string;
  title: string;
  fromRaw?: string | null;
  canQuickSend: boolean;
  hasTo: boolean;
  inquiryChannel?: InquiryChannel | null;
  badges?: string[];
  compact?: boolean;
  openHref?: string;
  onSent?: () => void;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [landMethodBairitsu, setLandMethodBairitsu] = useState(false);
  const [channel, setChannel] = useState<InquiryChannel | null>(
    inquiryChannelProp || null
  );
  const [loaded, setLoaded] = useState(false);

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
      setLoaded(true);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "下書き取得エラー");
    }
  }, [dealId]);

  useEffect(() => {
    if (open && !loaded) void loadPreview();
  }, [open, loaded, loadPreview]);

  if (!canQuickSend) return null;

  const bairitsuMissing =
    landMethodBairitsu &&
    channel === "agent_email" &&
    !body.includes(BAIRITSU_MARKER);

  const isHandoff = channel === "grok_handoff";

  async function send() {
    if (!checked) {
      setMsg("送信内容を確認してください");
      return;
    }
    if (!to.includes("@")) {
      setMsg("宛先メールを入力してください");
      return;
    }
    if (bairitsuMissing) {
      setMsg("倍率地域のため固定資産税依頼文が必要です");
      return;
    }
    setBusy(true);
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
        setMsg(data.error || "送信失敗");
      } else {
        setOpen(false);
        setChecked(false);
        setLoaded(false);
        setMsg("送信キューに入れました（問合せ：送信中）");
        onSent?.();
        router.refresh();
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(false);
    }
  }

  const badgeText =
    badges && badges.length > 0 ? badges.join(" · ") : null;
  const channelLabel = channel
    ? INQUIRY_CHANNEL_LABEL[channel]
    : null;

  return (
    <>
      <button
        type="button"
        className="btn"
        disabled={busy}
        onClick={() => setOpen(true)}
        style={{
          fontSize: 12,
          padding: compact ? "4px 8px" : undefined,
          background: isHandoff ? "#e0e7ff" : "#fef3c7",
          borderColor: isHandoff ? "#6366f1" : "#f59e0b",
        }}
        title={
          badgeText ||
          (isHandoff ? "Grokに問合せ依頼" : "テンプレで第一問合せ")
        }
      >
        {busy ? "…" : isHandoff ? "Grok依頼" : "問合せ"}
      </button>
      {open ? (
        <div
          role="dialog"
          aria-modal
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.45)",
            zIndex: 1000,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 16,
          }}
          onClick={() => !busy && setOpen(false)}
        >
          <div
            className="card"
            style={{
              maxWidth: 520,
              width: "100%",
              maxHeight: "90vh",
              overflow: "auto",
              padding: 16,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <strong>
              {isHandoff ? "Grokに問合せ依頼" : "クイック問合せ"}
            </strong>
            {channelLabel ? (
              <p className="meta" style={{ marginTop: 4 }}>
                経路: {channelLabel}
              </p>
            ) : null}
            <p className="meta" style={{ marginTop: 4 }}>
              {title.slice(0, 60)}
              {badgeText ? ` · ${badgeText}` : ""}
            </p>
            {isHandoff ? (
              <p className="meta" style={{ color: "#4338ca", marginTop: 8 }}>
                仲介メールが無いため、自分宛に依頼メールを送ります。Grok
                が拾って Web／調査します。
              </p>
            ) : null}
            {!hasTo && !isHandoff ? (
              <p className="meta" style={{ color: "#b45309", marginTop: 8 }}>
                宛先が空です。下記に入力してください。
              </p>
            ) : null}
            <label className="meta" style={{ display: "block", marginTop: 12 }}>
              宛先
              <input
                type="email"
                value={to}
                onChange={(e) => setTo(e.target.value)}
                readOnly={isHandoff}
                style={{
                  display: "block",
                  width: "100%",
                  marginTop: 4,
                  background: isHandoff ? "#f1f5f9" : undefined,
                }}
              />
            </label>
            <p className="meta" style={{ marginTop: 8 }}>
              件名: {subject || "（読込中…）"}
            </p>
            <pre
              className="meta"
              style={{
                whiteSpace: "pre-wrap",
                fontSize: 11,
                maxHeight: 200,
                overflow: "auto",
                marginTop: 8,
                padding: 8,
                background: "#f8fafc",
              }}
            >
              {body || "読込中…"}
            </pre>
            <label
              className="meta"
              style={{
                display: "flex",
                gap: 8,
                alignItems: "flex-start",
                marginTop: 12,
              }}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => setChecked(e.target.checked)}
              />
              <span>
                {isHandoff
                  ? "この内容で estate から自分宛に依頼してよい"
                  : "テンプレ内容で estate から仲介へ送信してよい"}
              </span>
            </label>
            {msg ? (
              <p className="meta" style={{ color: "#b91c1c", marginTop: 8 }}>
                {msg}
              </p>
            ) : null}
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 8,
                marginTop: 12,
              }}
            >
              <button
                type="button"
                className="btn"
                disabled={busy || !loaded}
                onClick={() => void send()}
              >
                {busy ? "送信中…" : "この内容で送信"}
              </button>
              {openHref ? (
                <a href={openHref} className="btn" style={{ fontSize: 13 }}>
                  詳細編集
                </a>
              ) : null}
              <button
                type="button"
                className="btn"
                disabled={busy}
                onClick={() => setOpen(false)}
              >
                閉じる
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
