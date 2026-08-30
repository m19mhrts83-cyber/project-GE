"use client";

import { useCallback, useEffect, useState } from "react";
import DealInquiryActions from "@/components/DealInquiryActions";
import DealReviewActions from "@/components/DealReviewActions";
import GrokInvestigateCopy from "@/components/GrokInvestigateCopy";
import { formatJstDateTime, fmtYen } from "@/lib/format";
import {
  formatMatchScore,
  scoreBand,
  scoreBandLabel,
} from "@/lib/reDealScoreUi";
import { isBuyPushDeal, isInProgressDeal } from "@/lib/reDealPursue";
import {
  DEAL_STATUS_LABEL,
  INQUIRY_STATUS_LABEL,
  dealGmailUrl,
  dealListingUrl,
  dealOriginLabel,
  dealRecommendedNext,
  dealScoreReasonLine,
  gmailDeepLink,
  grokOneLine,
} from "@/lib/rePipelineUi";
import type { InquiryChannel } from "@/lib/reInquiryChannel";

type TimelineItem = {
  kind: "message" | "event";
  occurred_at: string;
  direction?: string;
  event_type?: string;
  subject?: string;
  summary?: string;
  body_text?: string;
  gmail_id?: string | null;
  actor?: string;
};

type DealRow = {
  id: string;
  title: string;
  status: string;
  source: string;
  area?: string | null;
  structure?: string | null;
  price_man?: number | null;
  yield_pct?: number | null;
  match_score?: number | null;
  summary_json?: Record<string, unknown>;
  inquiry_status?: string | null;
};

type InquiryEval = {
  tier1: boolean;
  tier2: boolean;
  canQuickSend: boolean;
  hasTo: boolean;
  inquiryChannel?: InquiryChannel;
  badges: string[];
  reasons: string[];
};

export default function DealDetailDrawer({
  dealId,
  onClose,
}: {
  dealId: string;
  onClose: () => void;
}) {
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [deal, setDeal] = useState<DealRow | null>(null);
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [attachCount, setAttachCount] = useState(0);
  const [attachments, setAttachments] = useState<
    {
      id: string;
      filename: string;
      open_url?: string | null;
      kind?: string | null;
    }[]
  >([]);
  const [inquiryEval, setInquiryEval] = useState<InquiryEval | null>(null);
  const [expandedBody, setExpandedBody] = useState<Set<number>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const res = await fetch(`/api/re/deals/${dealId}/timeline`);
      const data = await res.json();
      if (!res.ok) {
        setErr(data.error || "読込失敗");
        return;
      }
      setDeal(data.deal);
      setTimeline(data.timeline || []);
      setAttachCount(data.attach_count || 0);
      setAttachments(data.attachments || []);
      setInquiryEval(data.inquiry_eval || null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "エラー");
    } finally {
      setLoading(false);
    }
  }, [dealId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const sj = (deal?.summary_json || {}) as Record<string, unknown>;
  const grok =
    sj.grok && typeof sj.grok === "object"
      ? (sj.grok as Record<string, unknown>)
      : null;
  const inquiryStatus =
    deal?.inquiry_status ||
    (typeof sj.inquiry_status === "string" ? sj.inquiry_status : "none");
  const originLabel = deal
    ? dealOriginLabel({
        title: deal.title,
        source: deal.source,
        summaryJson: sj,
      })
    : "";
  const nextAction = deal
    ? dealRecommendedNext({
        status: deal.status,
        title: deal.title,
        source: deal.source,
        inquiryStatus,
        summaryJson: sj,
        inquiryEval,
      })
    : null;
  const gmailUrl = dealGmailUrl(sj, deal?.source);
  const listingUrl = dealListingUrl(sj);
  const interestFormUrl =
    typeof sj.interest_form_url === "string" && sj.interest_form_url.trim()
      ? sj.interest_form_url.trim()
      : null;
  const scoreReason = deal
    ? dealScoreReasonLine({
        matchScore: deal.match_score,
        summaryJson: sj,
      })
    : "";
  const gmailReadAt =
    typeof sj.gmail_read_at === "string" ? sj.gmail_read_at : null;
  const opsFormDraft =
    sj.ops_form_draft && typeof sj.ops_form_draft === "object"
      ? (sj.ops_form_draft as {
          form_url?: string;
          missing_count?: number;
          markdown?: string;
        })
      : null;
  const OPS_FORM_URL =
    "https://form.os7.biz/f/1906a1a5/";
  const messages = timeline.filter((t) => t.kind === "message");
  const events = timeline.filter((t) => t.kind === "event");

  return (
    <>
      <div
        role="presentation"
        onClick={onClose}
        style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.35)",
          zIndex: 900,
        }}
      />
      <aside
        aria-label="案件詳細"
        style={{
          position: "fixed",
          top: 0,
          right: 0,
          width: "min(480px, 100vw)",
          height: "100vh",
          overflowY: "auto",
          background: "var(--bg, #fff)",
          borderLeft: "1px solid var(--border, #ccc)",
          zIndex: 901,
          padding: "16px 20px 32px",
          boxShadow: "-4px 0 24px rgba(0,0,0,0.12)",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: 8,
            marginBottom: 12,
          }}
        >
          <div>
            <p className="meta" style={{ margin: 0 }}>
              案件詳細
            </p>
            <h2 style={{ margin: "4px 0 0", fontSize: "1.1rem" }}>
              {deal?.title || "…"}
            </h2>
          </div>
          <button type="button" className="btn" onClick={onClose}>
            閉じる
          </button>
        </div>

        {loading ? (
          <p className="meta">読込中…</p>
        ) : err ? (
          <p className="meta" style={{ color: "var(--danger, #b45309)" }}>
            {err}
          </p>
        ) : deal ? (
          <>
            <div
              style={{
                marginBottom: 12,
                padding: "10px 12px",
                borderRadius: 8,
                background: "#eff6ff",
                border: "1px solid #bfdbfe",
              }}
            >
              <div style={{ fontSize: 13, fontWeight: 600 }}>
                出所: {originLabel}
              </div>
              {gmailReadAt ? (
                <p className="meta" style={{ margin: "4px 0 0" }}>
                  取込元メールは既読（問合せ送信済みではありません）
                </p>
              ) : null}
              {nextAction ? (
                <div style={{ marginTop: 10 }}>
                  <div className="meta" style={{ marginBottom: 2 }}>
                    いまやること
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.4 }}>
                    {nextAction.line}
                  </div>
                  <div className="meta" style={{ marginTop: 4 }}>
                    主操作の目安: {nextAction.primaryCta}
                  </div>
                </div>
              ) : null}
              <div style={{ marginTop: 12 }}>
                <div className="meta" style={{ marginBottom: 6 }}>
                  要約と突き合わせて確認（当面推奨）
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {gmailUrl ? (
                    <a
                      className="btn"
                      href={gmailUrl}
                      target="_blank"
                      rel="noreferrer"
                      style={{
                        fontWeight: 600,
                        background: "#1d4ed8",
                        color: "#fff",
                        borderColor: "#1d4ed8",
                      }}
                    >
                      元メールを開く
                    </a>
                  ) : (
                    <span className="meta">元メールなし</span>
                  )}
                  {interestFormUrl ? (
                    <a
                      className="btn"
                      href={interestFormUrl}
                      target="_blank"
                      rel="noreferrer"
                      style={{
                        fontWeight: 600,
                        background: "#0f766e",
                        color: "#fff",
                        borderColor: "#0f766e",
                      }}
                    >
                      紹介フォームを開く
                    </a>
                  ) : null}
                  {listingUrl ? (
                    <a
                      className="btn"
                      href={listingUrl}
                      target="_blank"
                      rel="noreferrer"
                      style={{
                        fontWeight: 600,
                        background: "#0f766e",
                        color: "#fff",
                        borderColor: "#0f766e",
                      }}
                    >
                      掲載ページを開く
                    </a>
                  ) : (
                    <span className="meta">掲載URLなし</span>
                  )}
                </div>
              </div>
            </div>

            <p className="meta">
              {DEAL_STATUS_LABEL[deal.status] || deal.status}
              {" · "}
              スコア {formatMatchScore(deal.match_score)}
              {(() => {
                const band = scoreBand(deal.match_score);
                return band !== "none" ? (
                  <span className="meta" style={{ marginLeft: 6 }}>
                    （{scoreBandLabel(band)}）
                  </span>
                ) : null;
              })()}
            </p>
            <p className="meta" style={{ marginTop: 2 }}>
              スコア根拠: {scoreReason}
            </p>
            <p className="meta">
              {deal.area || "—"} / {deal.structure || "—"} /{" "}
              {deal.price_man != null
                ? fmtYen(Number(deal.price_man) * 10000)
                : "—"}
            </p>

            {grok ? (
              <div className="card" style={{ marginTop: 12, padding: 12 }}>
                <strong>Grok 調査</strong>
                <p className="meta" style={{ marginTop: 6 }}>
                  {grokOneLine(grok)}
                </p>
                {typeof grok.population_table === "string" &&
                grok.population_table ? (
                  <p className="meta" style={{ marginTop: 4 }}>
                    人口動態: {String(grok.population_table).slice(0, 200)}
                  </p>
                ) : null}
                <details style={{ marginTop: 8 }}>
                  <summary className="meta">全文</summary>
                  <pre
                    className="meta"
                    style={{
                      whiteSpace: "pre-wrap",
                      fontSize: 12,
                      marginTop: 8,
                    }}
                  >
                    {JSON.stringify(grok, null, 2)}
                  </pre>
                </details>
              </div>
            ) : null}

            {inquiryStatus === "has_reply" ? (
              <div
                className="card"
                style={{
                  marginTop: 12,
                  padding: 12,
                  background: "#ecfdf5",
                  border: "1px solid #a7f3d0",
                }}
              >
                <strong>返信あり — 次の一手</strong>
                <ol
                  className="meta"
                  style={{ paddingLeft: 18, marginTop: 8, marginBottom: 8 }}
                >
                  <li>メール返信・添付 PDF を確認</li>
                  <li>「フォーム下書き」で不足項目を洗い出し</li>
                  <li>神大家個人 Drive に物件フォルダ＋写真</li>
                  <li>
                    <a
                      href={opsFormDraft?.form_url || OPS_FORM_URL}
                      target="_blank"
                      rel="noreferrer"
                    >
                      運営相談フォーム
                    </a>
                    （確認後に送信）
                  </li>
                  <li>809 運営回答 → 内見判断</li>
                </ol>
              </div>
            ) : null}

            {opsFormDraft?.markdown ? (
              <div className="card" style={{ marginTop: 12, padding: 12 }}>
                <strong>
                  フォーム下書き
                  {opsFormDraft.missing_count != null
                    ? `（不足 ${opsFormDraft.missing_count} 項目）`
                    : ""}
                </strong>
                <pre
                  className="meta"
                  style={{
                    whiteSpace: "pre-wrap",
                    fontSize: 11,
                    marginTop: 8,
                    maxHeight: 240,
                    overflow: "auto",
                  }}
                >
                  {opsFormDraft.markdown}
                </pre>
              </div>
            ) : null}

            <div className="card" style={{ marginTop: 12, padding: 12 }}>
              <strong>メールタイムライン</strong>
              {messages.length === 0 ? (
                <p className="meta" style={{ marginTop: 8 }}>
                  まだメッセージがありません
                </p>
              ) : (
                <ul
                  className="meta"
                  style={{ paddingLeft: 0, listStyle: "none", marginTop: 8 }}
                >
                  {messages.map((m, i) => {
                    const expanded = expandedBody.has(i);
                    const body = m.body_text || "";
                    const preview = body.slice(0, 500);
                    return (
                      <li
                        key={`m-${i}`}
                        style={{
                          marginBottom: 12,
                          paddingBottom: 12,
                          borderBottom: "1px solid var(--border, #eee)",
                        }}
                      >
                        <div>
                          {m.direction === "inbound" ? "← 返信" : "→ 送信"}{" "}
                          {formatJstDateTime(m.occurred_at)}
                        </div>
                        <div>{m.subject || "(無題)"}</div>
                        <div style={{ marginTop: 4 }}>
                          {expanded ? body : preview}
                          {body.length > 500 ? (
                            <button
                              type="button"
                              className="btn"
                              style={{
                                fontSize: 11,
                                padding: "2px 6px",
                                marginLeft: 6,
                              }}
                              onClick={() => {
                                const next = new Set(expandedBody);
                                if (expanded) next.delete(i);
                                else next.add(i);
                                setExpandedBody(next);
                              }}
                            >
                              {expanded ? "折りたたむ" : "全文"}
                            </button>
                          ) : null}
                        </div>
                        {m.gmail_id ? (
                          <a
                            href={gmailDeepLink(
                              m.gmail_id,
                              typeof sj.account === "string"
                                ? sj.account
                                : deal?.source
                            )}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Gmail ↗
                          </a>
                        ) : null}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            {attachCount > 0 ? (
              <div className="card" style={{ marginTop: 12, padding: 12 }}>
                <strong>証憑・添付（{attachCount}）</strong>
                <ul className="meta" style={{ paddingLeft: 18, marginTop: 8 }}>
                  {attachments.map((a) => (
                    <li key={a.id}>
                      {a.open_url ? (
                        <a href={a.open_url} target="_blank" rel="noreferrer">
                          {a.filename}
                        </a>
                      ) : (
                        a.filename
                      )}
                      {a.kind ? ` · ${a.kind}` : ""}
                    </li>
                  ))}
                </ul>
                <p className="meta" style={{ marginTop: 6 }}>
                  実体は Drive/OneDrive 証憑フォルダ（Supabase にはバイナリなし）
                </p>
              </div>
            ) : null}

            <div className="card" style={{ marginTop: 12, padding: 12 }}>
              <strong>判断履歴</strong>
              {events.length === 0 ? (
                <p className="meta" style={{ marginTop: 8 }}>
                  以降の操作から記録されます
                </p>
              ) : (
                <ul className="meta" style={{ paddingLeft: 18, marginTop: 8 }}>
                  {events.map((e, i) => (
                    <li key={`e-${i}`}>
                      {formatJstDateTime(e.occurred_at)}{" "}
                      · {e.summary || e.event_type}
                      {e.actor ? ` (${e.actor})` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="card" style={{ marginTop: 12, padding: 12 }}>
              {inquiryEval?.tier1 ? (
                <div
                  style={{
                    marginBottom: 10,
                    padding: "8px 10px",
                    borderRadius: 6,
                    background: "#eff6ff",
                    fontSize: 13,
                  }}
                >
                  <strong>問合せ候補（Tier1）</strong>
                  {inquiryEval.badges.length > 0 ? (
                    <span className="meta" style={{ marginLeft: 8 }}>
                      {inquiryEval.badges.join(" · ")}
                    </span>
                  ) : null}
                  {inquiryEval.tier2 ? (
                    <div className="meta" style={{ marginTop: 4 }}>
                      日次キュー（Tier2）対象 — 朝 digest で確認
                    </div>
                  ) : null}
                </div>
              ) : null}
              <strong>
                第一問合せ —{" "}
                {INQUIRY_STATUS_LABEL[inquiryStatus] || inquiryStatus}
              </strong>
              {nextAction &&
              (nextAction.code === "triage" ||
                nextAction.code === "hz_research") ? (
                <p className="meta" style={{ marginTop: 6 }}>
                  下の問合せ／Grok依頼は任意（推奨は上の「いまやること」）
                </p>
              ) : null}
              <div style={{ marginTop: 8 }}>
                <DealReviewActions
                  dealId={deal.id}
                  status={deal.status}
                  gmailId={
                    typeof sj.gmail_id === "string" ? sj.gmail_id : null
                  }
                  gmailUrl={gmailUrl}
                  gmailReadAt={gmailReadAt}
                  dealTitle={deal.title}
                  fromRaw={typeof sj.from === "string" ? sj.from : null}
                  inquiryReady={inquiryEval?.tier1}
                  inquiryHasTo={inquiryEval?.hasTo}
                  inquiryBadges={inquiryEval?.badges}
                  inquiryChannel={inquiryEval?.inquiryChannel}
                  inProgress={isInProgressDeal({
                    id: deal.id,
                    title: deal.title,
                    status: deal.status,
                    source: deal.source,
                    inquiry_status: inquiryStatus,
                    summary_json: sj,
                  })}
                  buyPush={isBuyPushDeal({
                    id: deal.id,
                    title: deal.title,
                    status: deal.status,
                    source: deal.source,
                    inquiry_status: inquiryStatus,
                    summary_json: sj,
                  })}
                />
              </div>
              {(deal.status === "info" || deal.status === "viewing") ? (
                <GrokInvestigateCopy
                  dealId={deal.id}
                  title={deal.title}
                  area={deal.area}
                  priceMan={
                    deal.price_man != null ? Number(deal.price_man) : null
                  }
                  summaryJson={sj}
                  alreadyGrok={deal.source === "mail_grok"}
                />
              ) : null}
              <DealInquiryActions
                dealId={deal.id}
                title={deal.title}
                fromRaw={typeof sj.from === "string" ? sj.from : null}
                inquiryStatus={inquiryStatus}
                messages={messages.map((m) => ({
                  direction: m.direction,
                  subject: m.subject,
                  from_email: undefined,
                  occurred_at: m.occurred_at,
                  body_text: m.body_text,
                }))}
                autoPassPendingRead={Boolean(sj.auto_pass_pending_read)}
                autoPassReason={
                  typeof sj.auto_pass_reason === "string"
                    ? sj.auto_pass_reason
                    : null
                }
              />
            </div>
          </>
        ) : null}
      </aside>
    </>
  );
}
