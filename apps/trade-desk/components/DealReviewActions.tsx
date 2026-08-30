"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import DealInquiryQuickButton from "@/components/DealInquiryQuickButton";
import type { InquiryChannel } from "@/lib/reInquiryChannel";

type Action = "confirm" | "pass" | "pursue_add" | "pursue_remove";

export default function DealReviewActions({
  dealId,
  status,
  gmailId,
  gmailUrl,
  gmailReadAt,
  dealTitle,
  fromRaw,
  inquiryReady,
  inquiryHasTo,
  inquiryBadges,
  inquiryChannel,
  openDealHref,
  pursuing,
  compactPursue,
}: {
  dealId: string;
  status: string;
  gmailId?: string | null;
  /** authuser 付き deep link（なければ gmailId から簡易 URL） */
  gmailUrl?: string | null;
  gmailReadAt?: string | null;
  dealTitle?: string;
  fromRaw?: string | null;
  inquiryReady?: boolean;
  inquiryHasTo?: boolean;
  inquiryBadges?: string[];
  inquiryChannel?: InquiryChannel | null;
  openDealHref?: string;
  /** いま買い進め中ブロックに出ている */
  pursuing?: boolean;
  /** 買い進めブロック内の「外す」だけ */
  compactPursue?: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<Action | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);

  async function run(action: Action) {
    if (action === "pass") {
      if (
        !window.confirm(
          "対象外（見送り）にします。よろしいですか？"
        )
      ) {
        return;
      }
    }
    if (action === "pursue_remove") {
      if (
        !window.confirm(
          "「いま買い進め中」から外します（見送りにはしません）。よろしいですか？"
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
        const labels: Record<Action, string> = {
          confirm: "確認しました",
          pass: "対象外にしました",
          pursue_add: "買い進め中に入れました",
          pursue_remove: "買い進め中から外しました",
        };
        setMsg(labels[action]);
        if (action === "confirm" || action === "pursue_add") setConfirmed(true);
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

  if (compactPursue) {
    return (
      <div style={{ minWidth: 100 }}>
        <button
          type="button"
          className="btn"
          disabled={busy !== null}
          onClick={() => run("pursue_remove")}
          style={{ fontSize: 12, padding: "4px 8px" }}
        >
          {busy === "pursue_remove" ? "…" : "外す"}
        </button>
        {msg ? (
          <div className="meta" style={{ marginTop: 4 }}>
            {msg}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div style={{ minWidth: 140 }}>
      {gmailId || gmailUrl ? (
        <div className="meta" style={{ marginBottom: 4 }}>
          <a
            href={
              gmailUrl ||
              `https://mail.google.com/mail/u/0/#all/${gmailId}`
            }
            target="_blank"
            rel="noreferrer"
          >
            Gmail
          </a>
          {alreadyRead ? " · 既読済" : " · 未既読"}
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
          {!pursuing && status !== "passed" ? (
            <button
              type="button"
              className="btn"
              disabled={busy !== null}
              onClick={() => run("pursue_add")}
              style={{ fontSize: 12, padding: "4px 8px" }}
              title="いま買い進め中ブロックに入れる"
            >
              {busy === "pursue_add" ? "…" : "買い進めへ"}
            </button>
          ) : null}
          {pursuing ? (
            <button
              type="button"
              className="btn"
              disabled={busy !== null}
              onClick={() => run("pursue_remove")}
              style={{ fontSize: 12, padding: "4px 8px" }}
            >
              {busy === "pursue_remove" ? "…" : "買い進め外す"}
            </button>
          ) : null}
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
