"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import DealInquiryQuickButton from "@/components/DealInquiryQuickButton";
import type { InquiryChannel } from "@/lib/reInquiryChannel";

type Action =
  | "confirm"
  | "pass"
  | "pursue_add"
  | "pursue_remove"
  | "set_viewing"
  | "set_offer";

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
  inProgress,
  buyPush,
  compactPursue,
  onInquiryChanged,
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
  /** 進行中（詳細〜内見）ブロックに出ている */
  inProgress?: boolean;
  /** 買い進め（買付・融資）ブロックに出ている */
  buyPush?: boolean;
  /** @deprecated inProgress を使う */
  pursuing?: boolean;
  /** 進行中／買い進めブロック内の「外す」だけ */
  compactPursue?: boolean;
  onInquiryChanged?: () => void;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<Action | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);

  const onInProgress = Boolean(inProgress);
  const st = String(status || "info");
  const showSetViewing =
    st !== "viewing" &&
    st !== "offer" &&
    st !== "loan" &&
    st !== "purchased" &&
    st !== "passed" &&
    st !== "archived";
  // 買付へ: viewing 推奨。info からも可（イレギュラーはチャットで）
  const allowOffer = st === "viewing" || st === "info";

  async function run(action: Action) {
    if (action === "pass") {
      if (!window.confirm("見送り（候補から外す）にします。よろしいですか？")) {
        return;
      }
    }
    if (action === "pursue_remove") {
      if (
        !window.confirm(
          "「進行中」から外します（見送りにはしません）。よろしいですか？"
        )
      ) {
        return;
      }
    }
    if (action === "set_offer") {
      if (
        !window.confirm(
          "買付へ進めます（買い進め＝買付証明・融資のフェーズ）。よろしいですか？"
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
          confirm: "確認しました（次は詳細問合せ）",
          pass: "見送りにしました",
          pursue_add: "進行中に入れました",
          pursue_remove: "進行中から外しました",
          set_viewing: "内見にしました",
          set_offer: "買付（買い進め）にしました",
        };
        setMsg(labels[action]);
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
    <div style={{ minWidth: 160 }}>
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
            title="候補に残す。次は図面・マイソクの問合せ（内見ではない）"
          >
            {busy === "confirm" ? "…" : "確認した（問合せへ）"}
          </button>
          <button
            type="button"
            className="btn"
            disabled={busy !== null || status === "passed"}
            onClick={() => run("pass")}
            style={{ fontSize: 12, padding: "4px 8px" }}
            title="候補から外す（見送り）"
          >
            {busy === "pass" ? "…" : "見送り"}
          </button>
          {!onInProgress && status !== "passed" && !buyPush ? (
            <button
              type="button"
              className="btn"
              disabled={busy !== null}
              onClick={() => run("pursue_add")}
              style={{ fontSize: 12, padding: "4px 8px" }}
              title="進行中（詳細〜内見）ブロックに入れる"
            >
              {busy === "pursue_add" ? "…" : "進行中に入れる"}
            </button>
          ) : null}
          {onInProgress && !buyPush ? (
            <button
              type="button"
              className="btn"
              disabled={busy !== null}
              onClick={() => run("pursue_remove")}
              style={{ fontSize: 12, padding: "4px 8px" }}
            >
              {busy === "pursue_remove" ? "…" : "進行中から外す"}
            </button>
          ) : null}
          {showSetViewing ? (
            <button
              type="button"
              className="btn"
              disabled={busy !== null}
              onClick={() => run("set_viewing")}
              style={{ fontSize: 12, padding: "4px 8px" }}
              title="需給・融資を見ながら内見へ"
            >
              {busy === "set_viewing" ? "…" : "内見にする"}
            </button>
          ) : null}
          {allowOffer ? (
            <button
              type="button"
              className="btn"
              disabled={busy !== null}
              onClick={() => run("set_offer")}
              style={{ fontSize: 12, padding: "4px 8px" }}
              title="買付証明〜融資の買い進めフェーズへ"
            >
              {busy === "set_offer" ? "…" : "買付へ"}
            </button>
          ) : null}
        </div>
      ) : null}
      {showActions ? (
        <p className="meta" style={{ marginTop: 6, maxWidth: 220, lineHeight: 1.4 }}>
          「確認した」＝候補に残して問合せへ。「見送り」＝候補から外す（まだ内見でも買い進めでもありません）
        </p>
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
            onSent={onInquiryChanged}
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
