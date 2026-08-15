"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

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

  const status = inquiryStatus || "none";
  const canSend =
    status === "none" || status === "draft" || status === "";
  const showPack = !canSend || (messages || []).length > 0;

  const defaultBody = useMemo(
    () =>
      [
        "お世話になっております。物件情報の送付をよろしくお願いします。",
        "併せて、固定資産評価額、修繕履歴(時期/内容/金額)が分かる資料も送付いただけると幸いです。",
        "差し支えなければ、以下についてもご教授ください。よろしくお願いします。",
        "・売却理由",
        "・売却希望時期",
        "・価格交渉可能でしょうか",
      ].join("\n"),
    []
  );
  const [subject, setSubject] = useState(
    `物件資料のご依頼（${title.slice(0, 40)}${title.length > 40 ? "…" : ""}）`
  );
  const [body, setBody] = useState(defaultBody);

  async function send() {
    if (!checked) {
      setMsg("確認チェックを入れてください");
      return;
    }
    if (!to.includes("@")) {
      setMsg("宛先メールを入力してください");
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
            onClick={() => {
              setOpen((v) => !v);
              setStep("edit");
              setChecked(false);
            }}
          >
            第一問い合わせ
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
                From: admin@livingsupport-matsu.co.jp
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
                From: admin@livingsupport-matsu.co.jp
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
