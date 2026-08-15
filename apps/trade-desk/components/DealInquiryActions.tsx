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
}: {
  dealId: string;
  title: string;
  fromRaw?: string | null;
  inquiryStatus?: string | null;
  messages?: Msg[] | null;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [to, setTo] = useState(() => parseEmail(fromRaw || undefined));
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const status = inquiryStatus || "none";
  const canSend = status === "none" || status === "draft";

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
    if (!to.includes("@")) {
      setMsg("宛先メールを入力してください");
      return;
    }
    if (
      !window.confirm(
        `admin から不動産会社へ第一問い合わせを送信します。\nTo: ${to}\n件名: ${subject}\n\nこの内容で送信してよいですか？`
      )
    ) {
      return;
    }
    setBusy("send");
    setMsg(null);
    try {
      const res = await fetch(`/api/re/deals/${dealId}/inquiry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "send",
          to,
          subject,
          body,
          ui_confirmed: true,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMsg(data.error || "失敗");
      } else {
        setMsg("送信ジョブをキューしました（Mac worker）");
        setOpen(false);
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

  return (
    <div style={{ minWidth: 160 }}>
      <div className="meta" style={{ marginBottom: 4 }}>
        問合せ: {status}
      </div>
      {canSend ? (
        <button
          type="button"
          className="btn primary"
          style={{ fontSize: 12, padding: "4px 8px", marginBottom: 4 }}
          disabled={busy !== null}
          onClick={() => setOpen((v) => !v)}
        >
          第一問い合わせ
        </button>
      ) : (
        <button
          type="button"
          className="btn"
          style={{ fontSize: 12, padding: "4px 8px", marginBottom: 4 }}
          disabled={busy !== null}
          onClick={pack}
        >
          {busy === "pack" ? "…" : "運営相談パック"}
        </button>
      )}
      {open ? (
        <div
          style={{
            marginTop: 8,
            padding: 8,
            border: "1px solid var(--border, #ccc)",
            borderRadius: 6,
            maxWidth: 360,
          }}
        >
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
            From: admin@livingsupport-matsu.co.jp（確認後に送信）
          </p>
          <button
            type="button"
            className="btn primary"
            disabled={busy !== null}
            onClick={send}
            style={{ marginTop: 6 }}
          >
            {busy === "send" ? "送信中…" : "確認して送信キューへ"}
          </button>
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
