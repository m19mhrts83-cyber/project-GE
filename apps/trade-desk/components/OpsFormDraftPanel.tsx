"use client";

import { useMemo, useState } from "react";

export type OpsFormFilledItem = {
  id?: string;
  label?: string;
  value?: string;
  source?: string;
};

export type OpsFormDraftData = {
  form_url?: string;
  missing_count?: number;
  filled_count?: number;
  markdown?: string;
  filled?: OpsFormFilledItem[];
  missing?: string[];
  at?: string;
};

export type OpsFormFillData = {
  at?: string;
  status?: string;
  filled_count?: number;
  note?: string;
  error?: string;
};

export type OpsConsultMeta = {
  stage?: string;
  label?: string;
  submittedAt?: string | null;
};

const OPS_FORM_URL = "https://form.os7.biz/f/1906a1a5/";

function parseFilledFromMarkdown(md: string): OpsFormFilledItem[] {
  const items: OpsFormFilledItem[] = [];
  for (const line of md.split("\n")) {
    const m = line.match(/^\s*·\s*(?:\[(?:override|suggest|profile|auto|reply|template)\]\s*)?(.+?):\s*(.*)$/);
    if (m) {
      items.push({ label: m[1].trim(), value: m[2].trim() });
    }
  }
  return items;
}

export default function OpsFormDraftPanel({
  dealId,
  draft,
  fill,
  consult,
  onQueued,
}: {
  dealId: string;
  draft: OpsFormDraftData | null;
  fill?: OpsFormFillData | null;
  consult?: OpsConsultMeta | null;
  onQueued?: () => void;
}) {
  const [busy, setBusy] = useState<"fill" | "draft" | "submitted" | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [submittedLocal, setSubmittedLocal] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const filled = useMemo(() => {
    if (!draft) return [];
    if (Array.isArray(draft.filled) && draft.filled.length > 0) {
      return draft.filled.filter((f) => (f.value || "").trim());
    }
    if (draft.markdown) return parseFilledFromMarkdown(draft.markdown);
    return [];
  }, [draft]);

  const formUrl = draft?.form_url || OPS_FORM_URL;

  if (!draft?.markdown && filled.length === 0) {
    return null;
  }

  async function copyText(text: string, key: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(key);
      setTimeout(() => setCopiedId(null), 1500);
    } catch {
      setMsg("コピーに失敗しました");
    }
  }

  async function copyAll() {
    const block = filled
      .map((f) => `${f.label || f.id || "項目"}:\n${f.value || ""}`)
      .join("\n\n---\n\n");
    await copyText(block, "__all__");
  }

  const isSubmitted =
    submittedLocal ||
    consult?.stage === "submitted" ||
    consult?.stage === "answered";

  async function queueAction(
    action: "form_fill" | "form_draft" | "ops_form_submitted"
  ) {
    setBusy(
      action === "form_fill"
        ? "fill"
        : action === "ops_form_submitted"
          ? "submitted"
          : "draft"
    );
    setMsg(null);
    try {
      const res = await fetch(`/api/re/deals/${dealId}/inquiry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMsg(typeof data?.error === "string" ? data.error : "キュー失敗");
      } else if (action === "ops_form_submitted") {
        setSubmittedLocal(true);
        setMsg("運営相談送信済として記録しました（一覧で区分表示）");
        onQueued?.();
      } else {
        setMsg(
          action === "form_fill"
            ? "転記ジョブをキューしました（Mac実行→ブラウザ入力・送信はしません）"
            : "下書き再生成をキューしました"
        );
        onQueued?.();
      }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "エラー");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div
      className="card"
      style={{
        marginTop: 12,
        padding: 12,
        border: isSubmitted ? "1px solid #f59e0b" : "1px solid #a7f3d0",
        background: isSubmitted ? "#fffbeb" : "#f0fdf4",
      }}
    >
      <strong style={{ fontSize: 14 }}>
        運営相談フォーム
        {consult?.label ? ` — ${consult.label}` : ""}
        {!consult?.label && draft?.missing_count != null
          ? `（不足 ${draft.missing_count} 項目）`
          : ""}
      </strong>

      <ol
        className="meta"
        style={{ paddingLeft: 18, marginTop: 8, marginBottom: 10, lineHeight: 1.5 }}
      >
        <li>下書きを確認（下の一覧）</li>
        <li>
          <strong>運営フォームへ転記</strong>（自動入力・送信しない）
        </li>
        <li>ブラウザで最終確認 → 送信</li>
        <li>送信後「運営相談を送信した」で記録（一覧で区分）</li>
      </ol>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 10 }}>
        <button
          type="button"
          className="btn"
          style={{
            fontSize: 13,
            padding: "6px 12px",
            background: "#059669",
            color: "#fff",
            border: "none",
            fontWeight: 600,
          }}
          disabled={busy !== null || filled.length === 0}
          onClick={() => queueAction("form_fill")}
        >
          {busy === "fill" ? "…" : "運営フォームへ転記"}
        </button>
        <button
          type="button"
          className="btn"
          style={{
            fontSize: 13,
            padding: "6px 12px",
            background: isSubmitted ? "#d97706" : "#b45309",
            color: "#fff",
            border: "none",
            fontWeight: 600,
          }}
          disabled={busy !== null || isSubmitted}
          onClick={() => queueAction("ops_form_submitted")}
        >
          {busy === "submitted"
            ? "…"
            : isSubmitted
              ? "運営相談送信済"
              : "運営相談を送信した"}
        </button>
        <button
          type="button"
          className="btn"
          style={{ fontSize: 12, padding: "4px 8px" }}
          onClick={() => window.open(formUrl, "_blank", "noopener,noreferrer")}
        >
          フォームを開く
        </button>
        <button
          type="button"
          className="btn"
          style={{ fontSize: 12, padding: "4px 8px" }}
          disabled={busy !== null || filled.length === 0}
          onClick={copyAll}
        >
          {copiedId === "__all__" ? "コピー済" : "一括コピー"}
        </button>
        <button
          type="button"
          className="btn"
          style={{ fontSize: 12, padding: "4px 8px" }}
          disabled={busy !== null}
          onClick={() => queueAction("form_draft")}
        >
          {busy === "draft" ? "…" : "下書き再生成"}
        </button>
      </div>

      {fill?.status ? (
        <p className="meta" style={{ marginBottom: 8, color: "#065f46" }}>
          転記状態: {fill.status}
          {fill.filled_count != null ? `（${fill.filled_count}項目）` : ""}
          {fill.note ? ` — ${fill.note}` : ""}
          {fill.error ? ` / エラー: ${fill.error}` : ""}
        </p>
      ) : null}
      {msg ? (
        <p className="meta" style={{ marginBottom: 8, color: "#1e40af" }}>
          {msg}
        </p>
      ) : null}
      <p className="meta" style={{ marginBottom: 8 }}>
        自動入力が一部失敗しても、下の「コピー」で貼り付けできます。
      </p>

      <div
        style={{
          maxHeight: 420,
          overflowY: "auto",
          border: "1px solid #bbf7d0",
          borderRadius: 6,
          background: "#fff",
        }}
      >
        {filled.map((f, i) => {
          const key = f.id || `i${i}`;
          const val = f.value || "";
          const long = val.length > 120 || val.includes("\n");
          const open = expanded[key] || !long;
          return (
            <div
              key={key}
              style={{
                padding: "8px 10px",
                borderBottom: "1px solid #ecfdf5",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: 8,
                  alignItems: "flex-start",
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: 11,
                      fontWeight: 700,
                      color: "#065f46",
                      marginBottom: 2,
                    }}
                  >
                    {f.label || f.id || `項目${i + 1}`}
                  </div>
                  <div
                    className="meta"
                    style={{
                      fontSize: 12,
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                      lineHeight: 1.4,
                      maxHeight: open ? undefined : 40,
                      overflow: open ? "visible" : "hidden",
                    }}
                  >
                    {val}
                  </div>
                  {long ? (
                    <button
                      type="button"
                      className="meta"
                      style={{
                        border: "none",
                        background: "none",
                        padding: 0,
                        color: "#2563eb",
                        cursor: "pointer",
                        fontSize: 11,
                        marginTop: 2,
                      }}
                      onClick={() =>
                        setExpanded((prev) => ({ ...prev, [key]: !prev[key] }))
                      }
                    >
                      {open ? "折りたたむ" : "全文表示"}
                    </button>
                  ) : null}
                </div>
                <button
                  type="button"
                  className="btn"
                  style={{ fontSize: 11, padding: "2px 6px", flexShrink: 0 }}
                  onClick={() => copyText(val, key)}
                >
                  {copiedId === key ? "済" : "コピー"}
                </button>
              </div>
            </div>
          );
        })}
        {filled.length === 0 ? (
          <pre
            className="meta"
            style={{
              whiteSpace: "pre-wrap",
              fontSize: 11,
              margin: 0,
              padding: 8,
            }}
          >
            {draft?.markdown}
          </pre>
        ) : null}
      </div>
    </div>
  );
}
