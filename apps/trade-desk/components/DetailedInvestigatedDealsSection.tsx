"use client";

import { useState } from "react";
import Link from "next/link";
import {
  type PursueDealFields,
  type S3InvestigationData,
  type DealAttachmentInfo,
  type YieldDisplayInfo,
  type LandValueDisplayInfo,
  getYieldDisplayInfo,
  getLandValueDisplayInfo,
  getDealAttachments,
} from "@/lib/reDealPursue";

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

function getAttachmentLabel(fn: string, kind?: string | null) {
  if (
    kind === "mysoku" ||
    kind === "maisoku" ||
    fn.includes("中古戸建") ||
    fn.includes("マイソク") ||
    fn.includes("図面") ||
    fn.includes("概要書")
  ) {
    let clean = fn.replace(/\.PDF|\.pdf/gi, "");
    if (clean.includes("向山89_物件概要書")) clean = "89番 概要書(マイソク)";
    else if (clean.includes("向山78_物件概要書")) clean = "78番 概要書(マイソク)";
    else if (clean.length > 16) clean = clean.slice(0, 15) + "…";
    return { label: `📄 ${clean}`, highlight: true, bg: "#eff6ff", border: "#3b82f6", color: "#1d4ed8" };
  }
  if (kind === "contract" || fn.includes("契約書")) {
    return { label: "📑 賃貸借契約書", highlight: true, bg: "#f5f3ff", border: "#8b5cf6", color: "#6d28d9" };
  }
  if (fn.includes("評価証明")) {
    return { label: "📋 評価証明書", highlight: false, bg: "#ecfdf5", border: "#10b981", color: "#047857" };
  }
  if (fn.includes("謄本") || fn.includes("公図") || fn.includes("測量図")) {
    let clean = fn.replace(/\(白塗り\)|\.PDF|\.pdf/gi, "");
    if (clean.length > 16) clean = clean.slice(0, 15) + "…";
    return { label: `📐 ${clean}`, highlight: false, bg: "#f8fafc", border: "#cbd5e1", color: "#334155" };
  }
  if (fn.includes("住宅地図") || fn.includes("地図")) {
    let clean = fn.replace(/\.PDF|\.pdf/gi, "");
    if (clean.includes("向山89")) clean = "89番 住宅地図";
    else if (clean.includes("向山78")) clean = "78番 住宅地図";
    else if (clean.length > 16) clean = clean.slice(0, 15) + "…";
    return { label: `🗺️ ${clean}`, highlight: false, bg: "#f0fdf4", border: "#86efac", color: "#166534" };
  }
  if (fn.includes("写真")) {
    let clean = fn.replace(/\.PDF|\.pdf/gi, "");
    if (clean.includes("向山89")) clean = "89番 写真PDF";
    else if (clean.includes("向山78")) clean = "78番 写真PDF";
    else if (clean.length > 16) clean = clean.slice(0, 15) + "…";
    return { label: `📷 ${clean}`, highlight: false, bg: "#fffbeb", border: "#fde68a", color: "#92400e" };
  }
  if (fn.includes("レポート")) {
    let clean = fn.replace(/\.PDF|\.pdf/gi, "").replace(/向山89_/, "");
    if (clean.length > 16) clean = clean.slice(0, 15) + "…";
    return { label: `📊 ${clean}`, highlight: false, bg: "#f5f3ff", border: "#ddd6fe", color: "#5b21b6" };
  }
  let clean = fn.replace(/\.PDF|\.pdf/gi, "");
  if (clean.length > 15) clean = clean.slice(0, 14) + "…";
  return { label: `📎 ${clean}`, highlight: false, bg: "#f8fafc", border: "#cbd5e1", color: "#475569" };
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
        <strong>「内見に行くか」「神大家さん運営へ相談するか」</strong>の判断材料として、調査結果と<strong>マイソクPDF・利回り</strong>を横並びで比較・確認できます。
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
              minWidth: 1160,
              borderCollapse: "collapse",
              fontSize: 13,
            }}
          >
            <thead>
              <tr style={{ background: "#e0e7ff", borderBottom: "2px solid #c7d2fe" }}>
                <th style={{ padding: "8px 6px", width: 48, textAlign: "center" }}>No.</th>
                <th style={{ padding: "8px 10px", width: 105 }}>Grok判定</th>
                <th style={{ padding: "8px 10px", width: 190 }}>物件 / 所在地</th>
                <th style={{ padding: "8px 10px", width: 165 }}>価格 / 利回り / 土地値</th>
                <th style={{ padding: "8px 10px", width: 160 }}>返信・マイソクPDF</th>
                <th style={{ padding: "8px 10px", width: 130 }}>想定家賃 (S3需給)</th>
                <th style={{ padding: "8px 10px", width: 130 }}>ペルソナ (S5)</th>
                <th style={{ padding: "8px 10px", width: 150 }}>本線リスク・論点</th>
                <th style={{ padding: "8px 10px", width: 125 }}>ヒアリング事項</th>
                <th style={{ padding: "8px 10px", width: 75 }}>詳細</th>
              </tr>
            </thead>
            <tbody>
              {deals.map((d, index) => {
                const serialNo = index + 1;
                const sj = (d.summary_json as Record<string, unknown>) || {};
                const s3 = (sj.s3_investigation as S3InvestigationData) || {};
                const vStyle = verdictBadge(s3.verdict);
                const isQuestionsExpanded = expandedQuestionsDealId === d.id;
                const yieldInfo = getYieldDisplayInfo(d);
                const landInfo = getLandValueDisplayInfo(d);
                const attachments = getDealAttachments(d);
                const hasReply = d.inquiry_status === "has_reply" || attachments.length > 0;

                const priceStr =
                  d.price_man != null
                    ? `${d.price_man}万円`
                    : s3.structure && s3.structure.includes("万")
                    ? s3.structure.match(/\d+万/)?.[0] || "—"
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
                    {/* 0. シリアルナンバー */}
                    <td style={{ padding: "10px 4px", verticalAlign: "top", textAlign: "center" }}>
                      <span
                        style={{
                          display: "inline-block",
                          padding: "2px 6px",
                          borderRadius: 4,
                          fontSize: 12,
                          fontWeight: 800,
                          background: "#312e81",
                          color: "#fff",
                          minWidth: 32,
                        }}
                      >
                        #{serialNo}
                      </span>
                    </td>

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

                    {/* 3. 価格 / 利回り / 土地値 */}
                    <td style={{ padding: "10px 8px", verticalAlign: "top" }}>
                      <div style={{ fontWeight: 700, color: "#0f172a", fontSize: 14 }}>
                        {priceStr}
                      </div>
                      <div style={{ marginTop: 4 }}>
                        <span
                          style={{
                            display: "inline-block",
                            padding: "2px 6px",
                            borderRadius: 4,
                            fontSize: 11,
                            fontWeight: 700,
                            background: yieldInfo.badgeBg,
                            color: yieldInfo.badgeColor,
                            border: `1px solid ${yieldInfo.badgeBorder}`,
                          }}
                        >
                          {yieldInfo.label}
                        </span>
                      </div>
                      {yieldInfo.monthlyRentStr ? (
                        <div style={{ fontSize: 11, color: "#047857", marginTop: 2, fontWeight: 500 }}>
                          {yieldInfo.monthlyRentStr}
                        </div>
                      ) : null}
                      {yieldInfo.notes ? (
                        <div style={{ fontSize: 10, color: "#64748b", marginTop: 1 }}>
                          {yieldInfo.notes}
                        </div>
                      ) : null}

                      {/* 土地値情報 */}
                      {landInfo.hasData ? (
                        <div
                          style={{
                            marginTop: 6,
                            paddingTop: 5,
                            borderTop: "1px dashed #cbd5e1",
                          }}
                        >
                          <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
                            <span
                              style={{
                                display: "inline-block",
                                padding: "1px 6px",
                                borderRadius: 4,
                                fontSize: 11,
                                fontWeight: 800,
                                background: landInfo.badgeBg,
                                color: landInfo.badgeColor,
                                border: `1px solid ${landInfo.badgeBorder}`,
                              }}
                              title={landInfo.notes || ""}
                            >
                              {landInfo.badgeLabel}
                            </span>
                            {landInfo.basisUrl ? (
                              <a
                                href={landInfo.basisUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{
                                  fontSize: 10,
                                  color: "#2563eb",
                                  textDecoration: "underline",
                                }}
                                title="路線価図を開く"
                              >
                                路線図↗
                              </a>
                            ) : null}
                          </div>
                          {landInfo.appraisalManStr ? (
                            <div style={{ fontSize: 11, color: "#1e1b4b", marginTop: 2, fontWeight: 700 }}>
                              積算: {landInfo.appraisalManStr}
                            </div>
                          ) : null}
                          {landInfo.tsuboPriceStr ? (
                            <div style={{ fontSize: 10, color: "#475569", marginTop: 1 }}>
                              {landInfo.tsuboPriceStr}
                            </div>
                          ) : null}
                          {landInfo.landAreaStr ? (
                            <div style={{ fontSize: 10, color: "#64748b" }} title={landInfo.landAreaStr}>
                              地積: {landInfo.landAreaStr.split("（")[0]}
                            </div>
                          ) : null}
                        </div>
                      ) : (
                        <div style={{ marginTop: 4, fontSize: 10, color: "#94a3b8" }}>
                          土地値: 未算定
                        </div>
                      )}
                    </td>

                    {/* 4. 返信・マイソクPDF */}
                    <td style={{ padding: "10px 8px", verticalAlign: "top" }}>
                      <div style={{ marginBottom: 4 }}>
                        {hasReply ? (
                          <span
                            style={{
                              display: "inline-block",
                              padding: "2px 6px",
                              borderRadius: 4,
                              fontSize: 11,
                              fontWeight: 700,
                              background: "#d1fae5",
                              color: "#065f46",
                              border: "1px solid #10b981",
                            }}
                          >
                            ✅ 返信受領・資料あり
                          </span>
                        ) : (
                          <span
                            style={{
                              display: "inline-block",
                              padding: "2px 6px",
                              borderRadius: 4,
                              fontSize: 11,
                              background: "#e0f2fe",
                              color: "#0369a1",
                              border: "1px solid #7dd3fc",
                            }}
                          >
                            📨 返信待ち (未着)
                          </span>
                        )}
                      </div>

                      {attachments.length > 0 ? (
                        <div
                          style={{
                            display: "flex",
                            flexDirection: "column",
                            gap: 3,
                            maxHeight: 180,
                            overflowY: "auto",
                            paddingRight: 4,
                          }}
                        >
                          {attachments.map((a, idx) => {
                            const meta = getAttachmentLabel(a.filename, a.kind);
                            if (a.open_url) {
                              return (
                                <a
                                  key={`att-${idx}`}
                                  href={a.open_url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  title={`${a.filename} をGoogle Driveで開く`}
                                  style={{
                                    display: "inline-block",
                                    fontSize: 11,
                                    padding: "2px 6px",
                                    borderRadius: 4,
                                    textDecoration: "none",
                                    background: meta.bg,
                                    color: meta.color,
                                    border: `1px solid ${meta.border}`,
                                    fontWeight: meta.highlight ? 600 : 400,
                                  }}
                                >
                                  {meta.label} ↗
                                </a>
                              );
                            }
                            return (
                              <span
                                key={`att-${idx}`}
                                style={{
                                  fontSize: 11,
                                  color: "#64748b",
                                  padding: "1px 4px",
                                }}
                              >
                                {meta.label}
                              </span>
                            );
                          })}
                        </div>
                      ) : (
                        <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 4 }}>
                          受領PDF未着
                        </div>
                      )}
                    </td>

                    {/* 5. 想定家賃 (S3需給) */}
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
                        需給三次判断済
                      </div>
                    </td>

                    {/* 6. ペルソナ (S5) */}
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

                    {/* 7. 本線リスク・論点 */}
                    <td style={{ padding: "10px 8px", verticalAlign: "top" }}>
                      <div
                        style={{
                          fontSize: 12,
                          color: s3.key_risk ? "#b45309" : "#64748b",
                          background: s3.key_risk ? "#fffbeb" : "transparent",
                          padding: s3.key_risk ? "4px 6px" : 0,
                          borderRadius: 4,
                          border: s3.key_risk ? "1px solid #fde68a" : "none",
                        }}
                      >
                        {s3.key_risk ? (
                          <>
                            <strong>⚠️ 注目:</strong> {s3.key_risk}
                          </>
                        ) : (
                          <span style={{ color: "#94a3b8" }}>特記リスクなし</span>
                        )}
                      </div>
                    </td>

                    {/* 8. ヒアリング確認事項 */}
                    <td style={{ padding: "10px 8px", verticalAlign: "top" }}>
                      {s3.hearing_questions && s3.hearing_questions.length > 0 ? (
                        <div>
                          <div style={{ fontSize: 12, color: "#3730a3", fontWeight: 600 }}>
                            {s3.hearing_questions.length}項目の確認事項
                          </div>
                          <button
                            type="button"
                            onClick={() =>
                              setExpandedQuestionsDealId(
                                isQuestionsExpanded ? null : d.id
                              )
                            }
                            style={{
                              marginTop: 4,
                              fontSize: 11,
                              background: isQuestionsExpanded ? "#4f46e5" : "#e0e7ff",
                              color: isQuestionsExpanded ? "#fff" : "#4338ca",
                              border: "none",
                              borderRadius: 4,
                              padding: "2px 8px",
                              cursor: "pointer",
                            }}
                          >
                            {isQuestionsExpanded ? "▲ 閉じる" : "▼ 質問を見る"}
                          </button>
                        </div>
                      ) : (
                        <span style={{ color: "#94a3b8", fontSize: 11 }}>なし</span>
                      )}
                    </td>

                    {/* 9. 操作 */}
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
            gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))",
            gap: 16,
          }}
        >
          {deals.map((d, index) => {
            const serialNo = index + 1;
            const sj = (d.summary_json as Record<string, unknown>) || {};
            const s3 = (sj.s3_investigation as S3InvestigationData) || {};
            const vStyle = verdictBadge(s3.verdict);
            const yieldInfo = getYieldDisplayInfo(d);
            const landInfo = getLandValueDisplayInfo(d);
            const attachments = getDealAttachments(d);
            const hasReply = d.inquiry_status === "has_reply" || attachments.length > 0;
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
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span
                        style={{
                          background: "#312e81",
                          color: "#fff",
                          fontSize: 12,
                          fontWeight: 800,
                          padding: "2px 7px",
                          borderRadius: 4,
                        }}
                      >
                        #{serialNo}
                      </span>
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
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <span style={{ fontWeight: 700, fontSize: 16, color: "#1e1b4b" }}>
                        {d.price_man != null ? `${d.price_man}万円` : "—"}
                      </span>
                      <div style={{ marginTop: 2, display: "flex", gap: 4, justifyContent: "flex-end", flexWrap: "wrap" }}>
                        <span
                          style={{
                            padding: "1px 6px",
                            borderRadius: 4,
                            fontSize: 11,
                            fontWeight: 700,
                            background: yieldInfo.badgeBg,
                            color: yieldInfo.badgeColor,
                            border: `1px solid ${yieldInfo.badgeBorder}`,
                          }}
                        >
                          {yieldInfo.label}
                        </span>
                        {landInfo.hasData ? (
                          <span
                            style={{
                              padding: "1px 6px",
                              borderRadius: 4,
                              fontSize: 11,
                              fontWeight: 800,
                              background: landInfo.badgeBg,
                              color: landInfo.badgeColor,
                              border: `1px solid ${landInfo.badgeBorder}`,
                            }}
                            title={landInfo.notes || ""}
                          >
                            {landInfo.badgeLabel}
                          </span>
                        ) : null}
                      </div>
                      {landInfo.appraisalManStr ? (
                        <div style={{ fontSize: 10, color: "#475569", marginTop: 1, fontWeight: 600 }}>
                          積算: {landInfo.appraisalManStr}
                          {landInfo.tsuboPriceStr ? ` (${landInfo.tsuboPriceStr.split(" ")[0]})` : ""}
                        </div>
                      ) : null}
                    </div>
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

                  {/* 返信状況・マイソクPDFカード */}
                  <div
                    style={{
                      padding: "8px 10px",
                      borderRadius: 6,
                      background: hasReply ? "#f0fdf4" : "#f8fafc",
                      border: `1px solid ${hasReply ? "#86efac" : "#e2e8f0"}`,
                      marginBottom: 10,
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: hasReply ? "#15803d" : "#475569" }}>
                        {hasReply ? "✅ 仲介会社返信・マイソク受領済" : "📨 問合せ返信待ち（資料未着）"}
                      </span>
                      {yieldInfo.monthlyRentStr ? (
                        <span style={{ fontSize: 11, color: "#047857", fontWeight: 600 }}>
                          {yieldInfo.monthlyRentStr}
                        </span>
                      ) : null}
                    </div>

                    {attachments.length > 0 ? (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                        {attachments.map((a, idx) => {
                          const meta = getAttachmentLabel(a.filename, a.kind);
                          if (a.open_url) {
                            return (
                              <a
                                key={`card-att-${idx}`}
                                href={a.open_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{
                                  fontSize: 11,
                                  padding: "2px 8px",
                                  borderRadius: 4,
                                  textDecoration: "none",
                                  background: meta.bg,
                                  color: meta.color,
                                  border: `1px solid ${meta.border}`,
                                  fontWeight: meta.highlight ? 600 : 400,
                                }}
                              >
                                {meta.label} ↗
                              </a>
                            );
                          }
                          return null;
                        })}
                      </div>
                    ) : null}
                  </div>

                  {s3.verdict_reason ? (
                    <div
                      style={{
                        fontSize: 12,
                        color: "#334155",
                        background: "#f1f5f9",
                        padding: "6px 8px",
                        borderRadius: 4,
                        marginBottom: 10,
                        lineHeight: 1.4,
                      }}
                    >
                      {s3.verdict_reason}
                    </div>
                  ) : null}

                  {/* 土地値・積算情報 */}
                  {landInfo.hasData ? (
                    <div
                      style={{
                        fontSize: 12,
                        marginBottom: 8,
                        background: "#f8fafc",
                        padding: "6px 8px",
                        borderRadius: 4,
                        border: "1px solid #e2e8f0",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ color: "#475569" }}>
                          <strong style={{ color: "#1e293b" }}>土地値: </strong>
                          <span style={{ fontWeight: 800, color: landInfo.badgeColor }}>
                            {landInfo.ratioStr}
                          </span>
                          {landInfo.appraisalManStr ? ` (積算 ${landInfo.appraisalManStr})` : ""}
                        </span>
                        {landInfo.basisUrl ? (
                          <a
                            href={landInfo.basisUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{ fontSize: 11, color: "#2563eb", textDecoration: "underline" }}
                          >
                            路線価図 ↗
                          </a>
                        ) : null}
                      </div>
                      <div style={{ fontSize: 11, color: "#64748b", marginTop: 2 }}>
                        {landInfo.tsuboPriceStr ? <span>{landInfo.tsuboPriceStr}</span> : null}
                        {landInfo.landAreaStr ? <span style={{ marginLeft: 6 }}>/ 地積: {landInfo.landAreaStr}</span> : null}
                      </div>
                    </div>
                  ) : null}

                  {/* 需給・想定家賃 */}
                  <div style={{ fontSize: 12, marginBottom: 8 }}>
                    <span style={{ color: "#64748b" }}>想定家賃: </span>
                    <strong style={{ color: "#1e1b4b" }}>{s3.expected_rent || "—"}</strong>
                  </div>

                  {/* ペルソナ */}
                  {s3.persona?.target_class || s3.s5_persona_line ? (
                    <div style={{ fontSize: 12, marginBottom: 8, color: "#475569" }}>
                      <span style={{ color: "#64748b" }}>ターゲット: </span>
                      <strong>{s3.persona?.target_class || "ファミリー"}</strong>
                      {s3.persona?.age ? ` (${s3.persona.age})` : ""}
                      {s3.persona?.layout ? ` / ${s3.persona.layout}` : ""}
                      {s3.persona?.parking ? ` / P${s3.persona.parking}` : ""}
                    </div>
                  ) : null}

                  {/* リスク */}
                  {s3.key_risk ? (
                    <div
                      style={{
                        fontSize: 12,
                        color: "#b45309",
                        background: "#fffbeb",
                        padding: "6px 8px",
                        borderRadius: 4,
                        border: "1px solid #fde68a",
                        marginBottom: 10,
                      }}
                    >
                      <strong>⚠️ リスク:</strong> {s3.key_risk}
                    </div>
                  ) : null}

                  {/* ヒアリング確認事項 */}
                  {s3.hearing_questions && s3.hearing_questions.length > 0 ? (
                    <div style={{ marginTop: 8, borderTop: "1px dashed #e2e8f0", paddingTop: 8 }}>
                      <div
                        style={{
                          fontSize: 11,
                          fontWeight: 700,
                          color: "#4338ca",
                          marginBottom: 4,
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                        }}
                      >
                        <span>📋 神大家さん運営・仲介への確認事項 ({s3.hearing_questions.length}件)</span>
                        <button
                          type="button"
                          onClick={() => copyText(s3.hearing_questions!.join("\n"), `${d.title}の質問`)}
                          style={{
                            fontSize: 10,
                            padding: "1px 6px",
                            background: "#ede9fe",
                            color: "#6d28d9",
                            border: "1px solid #ddd6fe",
                            borderRadius: 4,
                            cursor: "pointer",
                          }}
                        >
                          コピー
                        </button>
                      </div>
                      <ul style={{ margin: 0, paddingLeft: 16, fontSize: 11, color: "#475569" }}>
                        {s3.hearing_questions.slice(0, 3).map((q, qIdx) => (
                          <li key={qIdx} style={{ marginBottom: 2 }}>
                            {q}
                          </li>
                        ))}
                        {s3.hearing_questions.length > 3 ? (
                          <li style={{ color: "#64748b", listStyle: "none" }}>
                            …他 {s3.hearing_questions.length - 3} 件
                          </li>
                        ) : null}
                      </ul>
                    </div>
                  ) : null}
                </div>

                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginTop: 12,
                    paddingTop: 8,
                    borderTop: "1px solid #f1f5f9",
                  }}
                >
                  <div style={{ display: "flex", gap: 8 }}>
                    {s3.portal_url ? (
                      <a
                        href={s3.portal_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontSize: 11, color: "#2563eb", textDecoration: "underline" }}
                      >
                        ポータル ↗
                      </a>
                    ) : null}
                    {obsidianUri ? (
                      <a
                        href={obsidianUri}
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
                        Obsidian
                      </a>
                    ) : null}
                  </div>
                  <Link href={getDealHref(d.id)} className="btn" style={{ fontSize: 12, padding: "3px 12px" }}>
                    詳細開く
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* 質問展開モーダル/アコーディオン (横並び一覧時) */}
      {viewMode === "table" && expandedQuestionsDealId ? (
        <div
          style={{
            marginTop: 12,
            padding: 12,
            background: "#fff",
            border: "1px solid #818cf8",
            borderRadius: 6,
            boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
          }}
        >
          {(() => {
            const currentDeal = deals.find((d) => d.id === expandedQuestionsDealId);
            if (!currentDeal) return null;
            const currentIdx = deals.findIndex((d) => d.id === expandedQuestionsDealId);
            const serialNo = currentIdx >= 0 ? currentIdx + 1 : null;
            const sj = (currentDeal.summary_json as Record<string, unknown>) || {};
            const s3 = (sj.s3_investigation as S3InvestigationData) || {};
            const questions = s3.hearing_questions || [];

            return (
              <div>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    borderBottom: "1px solid #e2e8f0",
                    paddingBottom: 6,
                    marginBottom: 8,
                  }}
                >
                  <strong style={{ fontSize: 13, color: "#1e1b4b" }}>
                    📋 {serialNo ? `[#${serialNo}] ` : ""}{currentDeal.title} — 神大家さん運営・仲介業者へのヒアリング確認事項（{questions.length}件）
                  </strong>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      type="button"
                      onClick={() => copyText(questions.join("\n"), `${currentDeal.title}の質問`)}
                      style={{
                        fontSize: 11,
                        background: "#d1fae5",
                        color: "#065f46",
                        border: "1px solid #10b981",
                        borderRadius: 4,
                        padding: "2px 8px",
                        cursor: "pointer",
                        fontWeight: 600,
                      }}
                    >
                      質問を一括コピー
                    </button>
                    <button
                      type="button"
                      onClick={() => setExpandedQuestionsDealId(null)}
                      style={{
                        fontSize: 11,
                        background: "#f1f5f9",
                        color: "#475569",
                        border: "1px solid #cbd5e1",
                        borderRadius: 4,
                        padding: "2px 8px",
                        cursor: "pointer",
                      }}
                    >
                      閉じる ✕
                    </button>
                  </div>
                </div>
                <ol style={{ margin: 0, paddingLeft: 20, fontSize: 12, color: "#334155", lineHeight: 1.6 }}>
                  {questions.map((q, idx) => (
                    <li key={idx} style={{ marginBottom: 4 }}>
                      {q}
                    </li>
                  ))}
                </ol>
              </div>
            );
          })()}
        </div>
      ) : null}
    </div>
  );
}
