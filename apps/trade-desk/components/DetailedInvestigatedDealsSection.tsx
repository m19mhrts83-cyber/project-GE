"use client";

import { useState } from "react";
import Link from "next/link";
import {
  type PursueDealFields,
  type S3InvestigationData,
} from "@/lib/reDealPursue";
import { fmtYen } from "@/lib/format";
import { formatMatchScore, scoreBand } from "@/lib/reDealScoreUi";

type Props = {
  deals: PursueDealFields[];
  currentTab?: string;
};

function verdictBadge(verdict?: string) {
  const v = (verdict || "").toLowerCase();
  if (v === "go") {
    return {
      label: "GO (推進)",
      bg: "#d1fae5",
      border: "#10b981",
      color: "#065f46",
    };
  }
  if (v === "hold") {
    return {
      label: "HOLD (保留・要確認)",
      bg: "#fef3c7",
      border: "#f59e0b",
      color: "#92400e",
    };
  }
  if (v === "pass") {
    return {
      label: "PASS (見送り)",
      bg: "#fee2e2",
      border: "#ef4444",
      color: "#991b1b",
    };
  }
  return {
    label: verdict || "調査済",
    bg: "#e0e7ff",
    border: "#818cf8",
    color: "#3730a3",
  };
}

export default function DetailedInvestigatedDealsSection({
  deals,
  currentTab,
}: Props) {
  const [viewMode, setViewMode] = useState<"table" | "cards">("table");
  const [expandedQuestionsDealId, setExpandedQuestionsDealId] = useState<
    string | null
  >(null);
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);

  if (deals.length === 0) return null;

  function getDealHref(id: string) {
    const q = new URLSearchParams();
    if (currentTab) q.set("tab", currentTab);
    q.set("deal", id);
    return `/realestate/deals?${q.toString()}`;
  }

  function copyText(text: string, label: string) {
    if (typeof navigator !== "undefined" && navigator.clipboard) {
      navigator.clipboard.writeText(text);
      setCopyFeedback(label);
      setTimeout(() => setCopyFeedback(null), 2000);
    }
  }

  return (
    <div
      className="card"
      style={{
        marginBottom: 20,
        borderColor: "#818cf8",
        background: "#faf5ff",
        borderWidth: 2,
        boxShadow: "0 4px 12px rgba(99, 102, 241, 0.08)",
      }}
    >
      <header
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "baseline",
          gap: 12,
          justifyContent: "space-between",
          borderBottom: "1px solid #e0e7ff",
          paddingBottom: 10,
          marginBottom: 10,
        }}
      >
        <div>
          <span
            style={{
              display: "inline-block",
              background: "#4f46e5",
              color: "#fff",
              fontSize: 11,
              fontWeight: 700,
              padding: "2px 8px",
              borderRadius: 4,
              marginRight: 8,
              letterSpacing: 0.5,
            }}
          >
            Grok × Obsidian 連携
          </span>
          <strong style={{ fontSize: 16, color: "#1e1b4b" }}>
            📌 詳細調査済・内見＆相談検討（{deals.length}件）
          </strong>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {copyFeedback ? (
            <span
              style={{
                fontSize: 12,
                color: "#059669",
                background: "#d1fae5",
                padding: "2px 8px",
                borderRadius: 4,
              }}
            >
              ✅ {copyFeedback} をコピーしました
            </span>
          ) : null}
          <div
            style={{
              display: "inline-flex",
              borderRadius: 6,
              border: "1px solid #cbd5e1",
              overflow: "hidden",
              fontSize: 12,
            }}
          >
            <button
              type="button"
              onClick={() => setViewMode("table")}
              style={{
                padding: "4px 10px",
                border: "none",
                background: viewMode === "table" ? "#4f46e5" : "#fff",
                color: viewMode === "table" ? "#fff" : "#475569",
                fontWeight: viewMode === "table" ? 600 : 400,
                cursor: "pointer",
              }}
            >
              横並び一覧
            </button>
            <button
              type="button"
              onClick={() => setViewMode("cards")}
              style={{
                padding: "4px 10px",
                border: "none",
                background: viewMode === "cards" ? "#4f46e5" : "#fff",
                color: viewMode === "cards" ? "#fff" : "#475569",
                fontWeight: viewMode === "cards" ? 600 : 400,
                cursor: "pointer",
              }}
            >
              並列カード比較
            </button>
          </div>
        </div>
      </header>

      <p className="meta" style={{ marginTop: 2, marginBottom: 12, color: "#475569", fontSize: 13 }}>
        問合せ返信を受け、Grok bot（S3需給三次・S5ペルソナ）で精査し、Obsidianに詳細レポートが蓄積された物件です。
        <strong>「内見に行くか」「神大家さん運営へ相談するか」</strong>の判断材料として、調査結果を横並びで比較・確認できます。
      </p>

      {viewMode === "table" ? (
        <div
          style={{
            overflowX: "auto",
            border: "1px solid #c7d2fe",
            borderRadius: 6,
            background: "#fff",
          }}
        >
          <table
            style={{
              margin: 0,
              width: "100%",
              minWidth: 1080,
              borderCollapse: "collapse",
              fontSize: 13,
            }}
          >
            <thead>
              <tr style={{ background: "#e0e7ff", borderBottom: "2px solid #c7d2fe" }}>
                <th style={{ padding: "8px 10px", width: 110 }}>Grok判定</th>
                <th style={{ padding: "8px 10px", width: 220 }}>物件 / 所在地</th>
                <th style={{ padding: "8px 10px", width: 110 }}>価格 / 利回り</th>
                <th style={{ padding: "8px 10px", width: 150 }}>想定家賃 (S3需給)</th>
                <th style={{ padding: "8px 10px", width: 170 }}>ペルソナ (S5)</th>
                <th style={{ padding: "8px 10px", width: 180 }}>本線リスク・論点</th>
                <th style={{ padding: "8px 10px", width: 150 }}>ヒアリング確認事項</th>
                <th style={{ padding: "8px 10px", width: 90 }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {deals.map((d) => {
                const sj = d.summary_json || {};
                const s3 = (sj.s3_investigation as S3InvestigationData) || {};
                const vStyle = verdictBadge(s3.verdict);
                const isQuestionsExpanded = expandedQuestionsDealId === d.id;

                const priceStr =
                  d.price_man != null
                    ? `${d.price_man}万円`
                    : s3.structure && s3.structure.includes("万")
                    ? s3.structure.match(/\d+万/)?.[0] || "—"
                    : "—";

                const yieldStr =
                  d.yield_pct != null
                    ? `${d.yield_pct}%`
                    : s3.structure && s3.structure.includes("%")
                    ? s3.structure.match(/[\d.]+\s*%/)?.[0] || "—"
                    : "—";

                const obsidianFile = s3.filename || "";
                const obsidianUri = obsidianFile
                  ? `obsidian://open?vault=500_Obsidian_r1&file=${encodeURIComponent(
                      `01_Journaling/☆Real_Estate_Pick/${obsidianFile.replace(/\.md$/, "")}`
                    )}`
                  : null;

                return (
                  <tr
                    key={`inv-${d.id}`}
                    style={{
                      borderBottom: "1px solid #e2e8f0",
                      background: isQuestionsExpanded ? "#f8fafc" : "#fff",
                    }}
                  >
                    {/* 1. Grok判定 */}
                    <td style={{ padding: "10px 8px", verticalAlign: "top" }}>
                      <div
                        style={{
                          display: "inline-block",
                          padding: "3px 8px",
                          borderRadius: 4,
                          fontSize: 12,
                          fontWeight: 700,
                          background: vStyle.bg,
                          color: vStyle.color,
                          border: `1px solid ${vStyle.border}`,
                          marginBottom: 4,
                        }}
                      >
                        {vStyle.label}
                      </div>
                      {s3.verdict_reason ? (
                        <div
                          style={{
                            fontSize: 11,
                            color: "#475569",
                            lineHeight: 1.35,
                            marginTop: 4,
                          }}
                          title={s3.verdict_reason}
                        >
                          {s3.verdict_reason.length > 55
                            ? `${s3.verdict_reason.slice(0, 52)}…`
                            : s3.verdict_reason}
                        </div>
                      ) : null}
                    </td>

                    {/* 2. 物件 / 所在地 */}
                    <td style={{ padding: "10px 8px", verticalAlign: "top" }}>
                      <div style={{ fontWeight: 600, color: "#1e293b", marginBottom: 3 }}>
                        <Link
                          href={getDealHref(d.id)}
                          style={{ color: "#312e81", textDecoration: "none" }}
                          onMouseOver={(e) => (e.currentTarget.style.textDecoration = "underline")}
                          onMouseOut={(e) => (e.currentTarget.style.textDecoration = "none")}
                        >
                          {d.title}
                        </Link>
                      </div>
                      {s3.address ? (
                        <div style={{ fontSize: 11, color: "#64748b", marginBottom: 4 }}>
                          📍 {s3.address}
                        </div>
                      ) : null}
                      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                        {s3.portal_url ? (
                          <a
                            href={s3.portal_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                              fontSize: 11,
                              color: "#2563eb",
                              textDecoration: "underline",
                            }}
                          >
                            ポータル掲載 ↗
                          </a>
                        ) : null}
                        {obsidianUri ? (
                          <a
                            href={obsidianUri}
                            title="Obsidianアプリでノートを開く"
                            style={{
                              fontSize: 11,
                              color: "#7c3aed",
                              background: "#f3e8ff",
                              padding: "1px 6px",
                              borderRadius: 4,
                              textDecoration: "none",
                              border: "1px solid #d8b4fe",
                            }}
                          >
                            📓 Obsidian
                          </a>
                        ) : null}
                      </div>
                    </td>

                    {/* 3. 価格 / 利回り / 構造 */}
                    <td style={{ padding: "10px 8px", verticalAlign: "top" }}>
                      <div style={{ fontWeight: 700, color: "#0f172a", fontSize: 14 }}>
                        {priceStr}
                      </div>
                      {yieldStr !== "—" ? (
                        <div style={{ fontSize: 12, color: "#059669", fontWeight: 600 }}>
                          利回り {yieldStr}
                        </div>
                      ) : null}
                      {s3.structure ? (
                        <div
                          style={{
                            fontSize: 11,
                            color: "#64748b",
                            marginTop: 2,
                            lineHeight: 1.3,
                          }}
                        >
                          {s3.structure.split("・").slice(0, 2).join("・")}
                        </div>
                      ) : null}
                    </td>

                    {/* 4. 想定家賃 (S3需給) */}
                    <td style={{ padding: "10px 8px", verticalAlign: "top" }}>
                      <div style={{ fontWeight: 700, color: "#1e1b4b" }}>
                        {s3.expected_rent ? (
                          s3.expected_rent.length > 40
                            ? s3.expected_rent.slice(0, 38) + "…"
                            : s3.expected_rent
                        ) : (
                          <span style={{ color: "#94a3b8" }}>—</span>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>
                        需給三次判断済（競合比較）
                      </div>
                    </td>

                    {/* 5. ペルソナ (S5) */}
                    <td style={{ padding: "10px 8px", verticalAlign: "top" }}>
                      {s3.persona?.target_class ? (
                        <div style={{ fontWeight: 600, color: "#1e293b", fontSize: 12 }}>
                          {s3.persona.target_class}
                          {s3.persona.age ? ` (${s3.persona.age})` : ""}
                        </div>
                      ) : null}
                      {s3.persona?.layout || s3.persona?.parking ? (
                        <div style={{ fontSize: 11, color: "#475569", marginTop: 2 }}>
                          {s3.persona.layout ? `間取: ${s3.persona.layout} ` : ""}
                          {s3.persona.parking ? `駐車: ${s3.persona.parking}` : ""}
                        </div>
                      ) : s3.s5_persona_line ? (
                        <div style={{ fontSize: 11, color: "#475569" }}>
                          {s3.s5_persona_line.slice(0, 40)}…
                        </div>
                      ) : (
                        <span style={{ color: "#94a3b8", fontSize: 11 }}>—</span>
                      )}
                    </td>

                    {/* 6. 本線リスク・論点 */}
                    <td style={{ padding: "10px 8px", verticalAlign: "top" }}>
                      <div
                        style={{
                          fontSize: 12,
                          color: s3.key_risk ? "#b45309" : "#64748b",
                          background: s3.key_risk ? "#fef3c7" : "transparent",
                          padding: s3.key_risk ? "3px 6px" : 0,
                          borderRadius: 4,
                          lineHeight: 1.35,
                        }}
                      >
                        {s3.key_risk || "大きな減額・規制リスクなし"}
                      </div>
                    </td>

                    {/* 7. ヒアリング確認事項 */}
                    <td style={{ padding: "10px 8px", verticalAlign: "top" }}>
                      {s3.hearing_questions && s3.hearing_questions.length > 0 ? (
                        <div>
                          <button
                            type="button"
                            onClick={() =>
                              setExpandedQuestionsDealId(isQuestionsExpanded ? null : d.id)
                            }
                            style={{
                              padding: "3px 8px",
                              fontSize: 11,
                              borderRadius: 4,
                              border: "1px solid #c7d2fe",
                              background: isQuestionsExpanded ? "#4f46e5" : "#eef2ff",
                              color: isQuestionsExpanded ? "#fff" : "#4338ca",
                              cursor: "pointer",
                              fontWeight: 600,
                            }}
                          >
                            {isQuestionsExpanded
                              ? "閉じる ▲"
                              : `内見・質問項目 (${s3.hearing_questions.length}件) ▼`}
                          </button>
                          {!isQuestionsExpanded && (
                            <div
                              style={{
                                fontSize: 11,
                                color: "#64748b",
                                marginTop: 4,
                                lineHeight: 1.25,
                              }}
                            >
                              ① {s3.hearing_questions[0].slice(0, 26)}…
                            </div>
                          )}
                        </div>
                      ) : (
                        <span style={{ color: "#94a3b8", fontSize: 11 }}>なし</span>
                      )}
                    </td>

                    {/* 8. 操作 */}
                    <td style={{ padding: "10px 8px", verticalAlign: "top", textAlign: "right" }}>
                      <Link
                        href={getDealHref(d.id)}
                        className="btn"
                        style={{
                          fontSize: 12,
                          padding: "3px 10px",
                          display: "inline-block",
                          whiteSpace: "nowrap",
                        }}
                      >
                        詳細開く
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        /* カード並列比較モード */
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
            gap: 16,
          }}
        >
          {deals.map((d) => {
            const sj = d.summary_json || {};
            const s3 = (sj.s3_investigation as S3InvestigationData) || {};
            const vStyle = verdictBadge(s3.verdict);
            const obsidianFile = s3.filename || "";
            const obsidianUri = obsidianFile
              ? `obsidian://open?vault=500_Obsidian_r1&file=${encodeURIComponent(
                  `01_Journaling/☆Real_Estate_Pick/${obsidianFile.replace(/\.md$/, "")}`
                )}`
              : null;

            return (
              <div
                key={`card-${d.id}`}
                style={{
                  border: "1px solid #c7d2fe",
                  borderRadius: 8,
                  background: "#fff",
                  padding: 14,
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  boxShadow: "0 2px 6px rgba(0,0,0,0.03)",
                }}
              >
                <div>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "flex-start",
                      marginBottom: 8,
                    }}
                  >
                    <span
                      style={{
                        padding: "2px 8px",
                        borderRadius: 4,
                        fontSize: 11,
                        fontWeight: 700,
                        background: vStyle.bg,
                        color: vStyle.color,
                        border: `1px solid ${vStyle.border}`,
                      }}
                    >
                      {vStyle.label}
                    </span>
                    <span style={{ fontWeight: 700, fontSize: 16, color: "#1e1b4b" }}>
                      {d.price_man != null ? `${d.price_man}万円` : "—"}
                    </span>
                  </div>

                  <strong style={{ fontSize: 14, color: "#1e293b", display: "block", marginBottom: 4 }}>
                    <Link href={getDealHref(d.id)} style={{ color: "#312e81", textDecoration: "none" }}>
                      {d.title}
                    </Link>
                  </strong>

                  {s3.address ? (
                    <div style={{ fontSize: 11, color: "#64748b", marginBottom: 8 }}>
                      📍 {s3.address}
                    </div>
                  ) : null}

                  {s3.verdict_reason ? (
                    <div
                      style={{
                        fontSize: 12,
                        color: "#334155",
                        background: "#f8fafc",
                        borderLeft: `3px solid ${vStyle.border}`,
                        padding: "4px 8px",
                        marginBottom: 10,
                        lineHeight: 1.4,
                      }}
                    >
                      {s3.verdict_reason}
                    </div>
                  ) : null}

                  <div style={{ fontSize: 12, marginBottom: 8 }}>
                    <span style={{ color: "#64748b" }}>想定家賃: </span>
                    <strong style={{ color: "#1e1b4b" }}>{s3.expected_rent || "—"}</strong>
                  </div>

                  <div style={{ fontSize: 12, marginBottom: 8 }}>
                    <span style={{ color: "#64748b" }}>ターゲット: </span>
                    <span style={{ color: "#1e293b" }}>
                      {s3.persona?.target_class || "—"} {s3.persona?.layout ? `(${s3.persona.layout})` : ""}
                    </span>
                  </div>

                  {s3.key_risk ? (
                    <div
                      style={{
                        fontSize: 11,
                        color: "#92400e",
                        background: "#fef3c7",
                        padding: "4px 8px",
                        borderRadius: 4,
                        marginBottom: 8,
                      }}
                    >
                      ⚠️ {s3.key_risk}
                    </div>
                  ) : null}

                  {s3.hearing_questions && s3.hearing_questions.length > 0 ? (
                    <div
                      style={{
                        fontSize: 11,
                        background: "#eef2ff",
                        padding: "6px 8px",
                        borderRadius: 4,
                        marginBottom: 10,
                      }}
                    >
                      <div style={{ fontWeight: 600, color: "#4338ca", marginBottom: 4 }}>
                        内見・相談用ヒアリング項目:
                      </div>
                      <ol style={{ margin: 0, paddingLeft: 16 }}>
                        {s3.hearing_questions.map((q, idx) => (
                          <li key={idx} style={{ marginBottom: 3, color: "#334155" }}>
                            {q}
                          </li>
                        ))}
                      </ol>
                    </div>
                  ) : null}
                </div>

                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    borderTop: "1px solid #f1f5f9",
                    paddingTop: 8,
                    marginTop: 6,
                  }}
                >
                  <div style={{ display: "flex", gap: 8 }}>
                    {obsidianUri ? (
                      <a
                        href={obsidianUri}
                        style={{
                          fontSize: 11,
                          color: "#7c3aed",
                          textDecoration: "underline",
                        }}
                      >
                        📓 Obsidianで開く
                      </a>
                    ) : null}
                    {s3.portal_url ? (
                      <a
                        href={s3.portal_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{
                          fontSize: 11,
                          color: "#2563eb",
                          textDecoration: "underline",
                        }}
                      >
                        ポータル ↗
                      </a>
                    ) : null}
                  </div>
                  <Link href={getDealHref(d.id)} className="btn" style={{ fontSize: 12, padding: "3px 10px" }}>
                    開く
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 展開されたヒアリング確認事項モーダル/インライン表示 */}
      {expandedQuestionsDealId ? (
        (() => {
          const deal = deals.find((d) => d.id === expandedQuestionsDealId);
          if (!deal) return null;
          const s3 = (deal.summary_json?.s3_investigation as S3InvestigationData) || {};
          const questions = s3.hearing_questions || [];

          return (
            <div
              style={{
                marginTop: 12,
                padding: 14,
                background: "#f8fafc",
                border: "1px solid #c7d2fe",
                borderRadius: 6,
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 8,
                }}
              >
                <strong style={{ fontSize: 13, color: "#312e81" }}>
                  📋 【{deal.title}】 内見・業者・神大家さん運営相談用ヒアリング確認リスト（全{questions.length}項目）
                </strong>
                <button
                  type="button"
                  onClick={() => setExpandedQuestionsDealId(null)}
                  style={{
                    fontSize: 12,
                    border: "none",
                    background: "transparent",
                    color: "#64748b",
                    cursor: "pointer",
                  }}
                >
                  ✕ 閉じる
                </button>
              </div>
              <ol style={{ margin: 0, paddingLeft: 20, fontSize: 12, color: "#1e293b", lineHeight: 1.6 }}>
                {questions.map((q, i) => (
                  <li key={i} style={{ marginBottom: 4 }}>
                    {q}
                  </li>
                ))}
              </ol>
              <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
                <button
                  type="button"
                  onClick={() =>
                    copyText(
                      questions.map((q, idx) => `${idx + 1}. ${q}`).join("\n"),
                      "質問リスト"
                    )
                  }
                  style={{
                    fontSize: 11,
                    padding: "3px 8px",
                    borderRadius: 4,
                    border: "1px solid #cbd5e1",
                    background: "#fff",
                    cursor: "pointer",
                  }}
                >
                  📋 質問リストをコピー
                </button>
                {s3.obsidian_path ? (
                  <button
                    type="button"
                    onClick={() => copyText(s3.obsidian_path || "", "Obsidianパス")}
                    style={{
                      fontSize: 11,
                      padding: "3px 8px",
                      borderRadius: 4,
                      border: "1px solid #cbd5e1",
                      background: "#fff",
                      cursor: "pointer",
                    }}
                  >
                    📓 Obsidianパスをコピー
                  </button>
                ) : null}
              </div>
            </div>
          );
        })()
      ) : null}
    </div>
  );
}
