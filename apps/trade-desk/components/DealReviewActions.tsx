"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import DealInquiryQuickButton from "@/components/DealInquiryQuickButton";

type Action = "confirm" | "pass";

export default function DealReviewActions({
  dealId,
  status,
  gmailId,
  gmailReadAt,
  dealTitle,
  fromRaw,
  inquiryReady,
  inquiryHasTo,
  inquiryBadges,
  inquiryChannel,
  openDealHref,
}: {
  dealId: string;
  status: string;
  gmailId?: string | null;
  gmailReadAt?: string | null;
  dealTitle?: string;
  fromRaw?: string | null;
  inquiryReady?: boolean;
  inquiryHasTo?: boolean;
  inquiryBadges?: string[];
  inquiryChannel?: "agent_email" | "grok_handoff" | "not_applicable" | null;
  openDealHref?: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<Action | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);

  async function run(action: Action) {
    if (action === "pass") {
      if (
        !window.confirm(
          "対象外（見送り）にします。紐づく Gmail を既読にします。よろしいですか？"
        )
      ) {
        return;
      }
    }
    setBusy(action);
    setMsg(null);
    try {
      const res = await fetch(`/api/re/deals/${dealId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "失敗しました");
      } else {
        const readNote = data.mark_read_queued
          ? "／Gmail既読をキュー"
          : data.mark_read_skipped
            ? `／既読スキップ（${data.mark_read_skipped}）`
            : "";
        setMsg(
          action === "confirm"
            ? `確認しました${readNote}`
            : `対象外にしました${readNote}`
        );
        if (action === "confirm") setConfirmed(true);
        router.refresh();
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(null);
    }
  }

  const alreadyRead = Boolean(gmailReadAt);
  const showActions = status !== "archived";
  const showInquiryCta = Boolean(
    inquiryReady &&
      inquiryChannel !== "not_applicable" &&
      (confirmed || status !== "passed")
  );

  return (
    <div style={{ minWidth: 140 }}>
      {gmailId ? (
        <div className="meta" style={{ marginBottom: 4 }}>
          <a
            href={`https://mail.google.com/mail/u/#all/${gmailId}`}
            target="_blank"
            rel="noreferrer"
          >
            Gmail
          </a>
          {alreadyRead ? " · 既読" : " · 未読"}
        </div>
      ) : (
        <div className="meta" style={{ marginBottom: 4 }}>
          メール紐づけなし
        </div>
      )}
      {showActions ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
          <button
            type="button"
            className="btn"
            disabled={busy !== null}
            onClick={() => run("confirm")}
            style={{ fontSize: 12, padding: "4px 8px" }}
          >
            {busy === "confirm" ? "…" : "確認した"}
          </button>
          <button
            type="button"
            className="btn"
            disabled={busy !== null || status === "passed"}
            onClick={() => run("pass")}
            style={{ fontSize: 12, padding: "4px 8px" }}
          >
            {busy === "pass" ? "…" : "対象外"}
          </button>
        </div>
      ) : null}
      {showInquiryCta ? (
        <div style={{ marginTop: 6 }}>
          <DealInquiryQuickButton
            dealId={dealId}
            title={dealTitle || dealId}
            fromRaw={fromRaw}
            canQuickSend
            hasTo={inquiryHasTo ?? Boolean(fromRaw && fromRaw.includes("@"))}
            inquiryChannel={inquiryChannel}
            badges={inquiryBadges}
            compact
            openHref={openDealHref}
          />
        </div>
      ) : null}
      {msg ? (
        <div className="meta" style={{ marginTop: 4, maxWidth: 200 }}>
          {msg}
        </div>
      ) : null}
    </div>
  );
}
