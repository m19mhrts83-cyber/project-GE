import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import DealReviewActions from "@/components/DealReviewActions";
import DealsDrawerHost from "@/components/DealsDrawerHost";
import RealEstateLaneNav from "@/components/RealEstateLaneNav";
import { createClient } from "@/lib/supabase/server";
import { fmtYen } from "@/lib/format";
import { readMacWatchStatus } from "@/lib/macWatchStatus";
import {
  DEAL_STATUS_LABEL,
  INQUIRY_STATUS_LABEL,
  SOURCE_BADGE,
  grokOneLine,
  lastActivityLine,
  parseDealsTab,
  type DealsTabId,
} from "@/lib/rePipelineUi";
import {
  evaluateInquiryCandidate,
  type ReDealForInquiry,
} from "@/lib/reInquiryCandidate";
import { loadInquiryAutoConfig } from "@/lib/reInquiryAutoConfig";
import { getTier2QueueSummary } from "@/lib/reInquiryTier2Queue";
import { dedupeAndPrioritizeDeals } from "@/lib/reDealDedupe";
import { filterBuyProgressDeals } from "@/lib/reDealPursue";
import {
  formatMatchScore,
  scoreBand,
  scoreBandLabel,
  scoreCellStyle,
  scoreHitsPreview,
} from "@/lib/reDealScoreUi";
import Link from "next/link";
import { Suspense } from "react";

export const dynamic = "force-dynamic";

const FUNNEL = ["info", "viewing", "offer", "loan", "purchased"] as const;

const TAB_LINKS: { id: DealsTabId; label: string }[] = [
  { id: "candidates", label: "候補" },
  { id: "all", label: "全ファネル" },
  { id: "passed", label: "見送り" },
];

function inquiryChipStyle(status: string): Record<string, string | number> {
  const base = {
    display: "inline-block",
    padding: "2px 8px",
    borderRadius: 4,
    fontSize: 12,
    border: "1px solid var(--border, #ccc)",
  };
  if (status === "has_reply") return { ...base, background: "#ecfdf5" };
  if (status === "awaiting_reply" || status === "sent")
    return { ...base, background: "#eff6ff" };
  return base;
}

export default async function RealEstateDealsPage({
  searchParams,
}: {
  searchParams?: Promise<{
    deal?: string;
    tab?: string;
    vendor?: string;
    inquiry?: string;
  }>;
}) {
  const sp = (await searchParams) || {};
  const highlightDeal = (sp.deal || "").trim();
  const tab = parseDealsTab(sp.tab);
  const vendorFilter = (sp.vendor || "").trim();
  const inquiryFilter = (sp.inquiry || "").trim();

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const [{ data: deals }, { data: criteria }, { data: ops }, { data: buyPlan }] =
    await Promise.all([
      supabase
        .from("kurashift_re_deals")
        .select(
          "id, title, status, source, area, structure, price_man, yield_pct, match_score, updated_at, advice_json, summary_json, inquiry_status, inquiry_thread_id, inquiry_sent_at"
        )
        .order("match_score", { ascending: false, nullsFirst: false })
        .order("updated_at", { ascending: false })
        .limit(200),
      supabase
        .from("kurashift_buy_plan_criteria")
        .select("kind, raw_text, sort_order, version_id")
        .order("sort_order", { ascending: true })
        .limit(40),
      supabase
        .from("kurashift_ops_consult_events")
        .select("occurred_at, subject, tags, snippet")
        .order("occurred_at", { ascending: false })
        .limit(8),
      supabase
        .from("kurashift_buy_plan_versions")
        .select("id, version_key, label")
        .eq("is_canonical", true)
        .maybeSingle(),
    ]);

  const watch = await readMacWatchStatus(120);
  const inquiryConfig = loadInquiryAutoConfig();

  function inquiryEval(d: ReDealForInquiry) {
    return evaluateInquiryCandidate(d, inquiryConfig);
  }

  let visibleDeals = (deals || []).filter((d) => {
    if (vendorFilter) {
      const sj =
        d.summary_json && typeof d.summary_json === "object"
          ? (d.summary_json as { vendor_id?: string })
          : {};
      if (sj.vendor_id !== vendorFilter) return false;
    }
    if (inquiryFilter === "has_reply") {
      const inq =
        d.inquiry_status ||
        (d.summary_json &&
        typeof d.summary_json === "object" &&
        typeof (d.summary_json as { inquiry_status?: string }).inquiry_status ===
          "string"
          ? (d.summary_json as { inquiry_status: string }).inquiry_status
          : "none");
      if (inq !== "has_reply") return false;
    }
    if (inquiryFilter === "ready") {
      if (!inquiryEval(d).tier1) return false;
      return true;
    }
    if (tab === "candidates") {
      if (d.status !== "info" && d.status !== "viewing") return false;
      // 受付終了メールは候補から外す（見送り反映前の保険）
      const title = String(d.title || "");
      if (
        title.includes("※受付終了※") ||
        title.includes("＊受付終了＊") ||
        title.includes("*受付終了*")
      ) {
        return false;
      }
      return true;
    }
    if (tab === "passed") return d.status === "passed";
    return d.status !== "archived";
  });

  const dedupedVisible = dedupeAndPrioritizeDeals(visibleDeals, {
    preferId: highlightDeal,
  });
  visibleDeals = dedupedVisible.deals;
  const dedupeHiddenCount = dedupedVisible.hiddenCount;

  const allDealIds = (deals || []).map((d) => d.id);

  const [{ data: dealMessages }, { data: dealEvents }] = await Promise.all([
      allDealIds.length > 0
        ? supabase
            .from("kurashift_re_deal_messages")
            .select(
              "deal_id, direction, kind, subject, from_email, occurred_at, body_text"
            )
            .in("deal_id", allDealIds)
            .order("occurred_at", { ascending: true })
            .limit(500)
        : Promise.resolve({ data: [] as Array<{ deal_id: string }> }),
      allDealIds.length > 0
        ? supabase
            .from("kurashift_re_deal_events")
            .select("deal_id, event_type, summary, occurred_at")
            .in("deal_id", allDealIds)
            .order("occurred_at", { ascending: false })
            .limit(400)
        : Promise.resolve({ data: [] as Array<{ deal_id: string }> }),
    ]);

  const messagesByDeal = new Map<
    string,
    Array<{
      direction?: string;
      subject?: string;
      occurred_at?: string;
      body_text?: string;
    }>
  >();
  for (const m of dealMessages || []) {
    const row = m as {
      deal_id: string;
      direction?: string;
      subject?: string;
      occurred_at?: string;
      body_text?: string;
    };
    const list = messagesByDeal.get(row.deal_id) || [];
    list.push(row);
    messagesByDeal.set(row.deal_id, list);
  }

  const eventsByDeal = new Map<
    string,
    Array<{ event_type?: string; summary?: string; occurred_at?: string }>
  >();
  for (const e of dealEvents || []) {
    const row = e as {
      deal_id: string;
      event_type?: string;
      summary?: string;
      occurred_at?: string;
    };
    const list = eventsByDeal.get(row.deal_id) || [];
    list.push(row);
    eventsByDeal.set(row.deal_id, list);
  }

  const candidateDeals = dedupeAndPrioritizeDeals(
    (deals || []).filter((d) => d.status === "info" || d.status === "viewing")
  ).deals;
  let needReply = 0;
  let grokPending = 0;
  let inquiryNone = 0;
  let inquiryReady = 0;
  let viewingCount = 0;
  for (const d of candidateDeals) {
    if (d.status === "viewing") viewingCount++;
    const inq = d.inquiry_status || "none";
    if (inq === "has_reply") needReply++;
    if (inq === "none" || inq === "draft") inquiryNone++;
    if (d.source !== "mail_grok") grokPending++;
  }
  for (const d of candidateDeals) {
    if (inquiryEval(d).tier1) inquiryReady++;
  }

  const tier2Summary = await getTier2QueueSummary(supabase);
  const tier2Count = tier2Summary.queue.length;

  const pursueDeals = filterBuyProgressDeals(
    dedupeAndPrioritizeDeals(
      (deals || []).filter(
        (d) =>
          d.status === "viewing" ||
          d.status === "offer" ||
          d.status === "loan" ||
          d.status === "purchased"
      )
    ).deals
  );

  const counts: Record<string, number> = {};
  for (const s of Object.keys(DEAL_STATUS_LABEL)) counts[s] = 0;
  for (const d of deals || []) {
    counts[d.status] = (counts[d.status] || 0) + 1;
  }

  const canonId = buyPlan?.id;
  const criteriaLines = (criteria || []).filter(
    (c) => !canonId || c.version_id === canonId
  );

  const slimTable = tab === "candidates";

  function tabHref(nextTab: DealsTabId) {
    const q = new URLSearchParams();
    q.set("tab", nextTab);
    if (highlightDeal) q.set("deal", highlightDeal);
    if (vendorFilter) q.set("vendor", vendorFilter);
    if (inquiryFilter) q.set("inquiry", inquiryFilter);
    return `/realestate/deals?${q.toString()}`;
  }

  function openDealHref(dealId: string) {
    const q = new URLSearchParams();
    q.set("tab", tab);
    q.set("deal", dealId);
    if (vendorFilter) q.set("vendor", vendorFilter);
    if (inquiryFilter) q.set("inquiry", inquiryFilter);
    return `/realestate/deals?${q.toString()}`;
  }

  return (
    <Shell active="/realestate" email={user?.email ?? null}>
      <RealEstateLaneNav active="b-funnel" />
      <p className="page-kicker">③-B · 実行</p>
      <h1>千三つファネル</h1>
      <p className="sub">
        検討中の物件候補は「候補」タブ。行の「開く」で返信・判断履歴・第一問合せ。
        表示は同一案件を1件にまとめ、優先はメール問合せ → Grok（Webフォーム）の順。
        「評価スコア」は買い進め条件との一致度（数値＋高/中/低）。
        業者開拓は <a href="/realestate/vendors">業者開拓ウォッチ</a>。
      </p>
      {vendorFilter ? (
        <p className="meta">
          業者フィルタ: {vendorFilter}{" "}
          <Link href={`/realestate/deals?tab=${tab}`}>解除</Link>
        </p>
      ) : null}
      {inquiryFilter === "has_reply" ? (
        <p className="meta">
          問合せフィルタ: 要返信のみ{" "}
          <Link href={`/realestate/deals?tab=${tab}`}>解除</Link>
        </p>
      ) : null}
      {inquiryFilter === "ready" ? (
        <p className="meta">
          問合せフィルタ: 問合せ候補（Tier1）{" "}
          <Link href={`/realestate/deals?tab=${tab}`}>解除</Link>
        </p>
      ) : null}
      <p className="meta" style={{ marginBottom: 12 }}>
        {watch.label} · <a href="/jobs">ジョブ一覧</a>
      </p>

      {pursueDeals.length > 0 ? (
        <div
          className="card"
          style={{
            marginBottom: 16,
            borderColor: "#86efac",
            background: "#f0fdf4",
          }}
        >
          <header>
            <span className="lvl">Pursue</span>
            <strong>いま買い進め中（{pursueDeals.length}）</strong>
          </header>
          <p className="meta" style={{ marginTop: 6, marginBottom: 8 }}>
            買付・融資・購入、または内見で問合せ進行／Grok「聞く」／「確認した」の物件。
            プラン全体は{" "}
            <Link href="/realestate/buy-plan">買い進めプラン</Link>。
          </p>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>段階</th>
                  <th>評価スコア</th>
                  <th>物件</th>
                  <th>エリア</th>
                  <th>価格</th>
                  <th>Grok</th>
                  <th>問合せ</th>
                  <th>詳細</th>
                </tr>
              </thead>
              <tbody>
                {pursueDeals.map((d) => {
                  const sj =
                    d.summary_json && typeof d.summary_json === "object"
                      ? (d.summary_json as Record<string, unknown>)
                      : {};
                  const grok =
                    sj.grok && typeof sj.grok === "object"
                      ? (sj.grok as Record<string, unknown>)
                      : null;
                  const inq =
                    d.inquiry_status ||
                    (typeof sj.inquiry_status === "string"
                      ? sj.inquiry_status
                      : "none");
                  const band = scoreBand(d.match_score);
                  const hits = scoreHitsPreview(sj.hits);
                  return (
                    <tr key={`pursue-${d.id}`} id={`pursue-${d.id}`}>
                      <td>
                        <strong>
                          {DEAL_STATUS_LABEL[d.status] || d.status}
                        </strong>
                      </td>
                      <td>
                        <div style={scoreCellStyle(band)}>
                          {formatMatchScore(d.match_score)}
                          {band !== "none" ? (
                            <span className="meta" style={{ marginLeft: 6 }}>
                              {scoreBandLabel(band)}
                            </span>
                          ) : null}
                        </div>
                        {hits ? (
                          <div className="meta" style={{ fontSize: 11 }}>
                            {hits}
                          </div>
                        ) : null}
                      </td>
                      <td>{d.title}</td>
                      <td className="meta">{d.area || "—"}</td>
                      <td className="meta">
                        {d.price_man != null
                          ? fmtYen(Number(d.price_man) * 10000)
                          : "—"}
                      </td>
                      <td className="meta">{grokOneLine(grok)}</td>
                      <td>
                        <span style={inquiryChipStyle(inq)}>
                          {INQUIRY_STATUS_LABEL[inq] || inq}
                        </span>
                      </td>
                      <td>
                        <Link href={openDealHref(d.id)} className="btn">
                          開く
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="card" style={{ marginBottom: 16 }}>
          <header>
            <span className="lvl">Pursue</span>
            <strong>いま買い進め中</strong>
          </header>
          <p className="meta" style={{ marginTop: 8 }}>
            まだ明示的な買い進め案件はありません。候補で「確認した」または問合せを進めると、ここに出ます。
          </p>
        </div>
      )}

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 8,
          marginBottom: 16,
        }}
      >
        {TAB_LINKS.map((t) => {
          const on = tab === t.id;
          return (
            <Link
              key={t.id}
              href={tabHref(t.id)}
              className={on ? "btn" : undefined}
              style={
                on
                  ? undefined
                  : {
                      padding: "4px 10px",
                      border: "1px solid var(--border, #ccc)",
                      borderRadius: 6,
                      textDecoration: "none",
                      fontSize: 13,
                    }
              }
            >
              {t.label}
            </Link>
          );
        })}
      </div>

      {tab === "candidates" ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <header>
            <span className="lvl">候補</span>
            <strong>要対応サマリー</strong>
          </header>
          <p className="meta" style={{ marginTop: 8 }}>
            要返信 {needReply} · 問合せ候補 {inquiryReady} · Grok未調査{" "}
            {grokPending} · 第一問合せ未送 {inquiryNone} · 内見候補{" "}
            {viewingCount}
            {needReply > 0 ? (
              <>
                {" "}
                ·{" "}
                <Link href="/realestate/deals?tab=candidates&inquiry=has_reply">
                  要返信のみ
                </Link>
              </>
            ) : null}
            {inquiryReady > 0 ? (
              <>
                {" "}
                ·{" "}
                <Link href="/realestate/deals?tab=candidates&inquiry=ready">
                  問合せ候補のみ
                </Link>
              </>
            ) : null}
            {tier2Summary.enabled && tier2Count > 0 ? (
              <>
                {" "}
                ·{" "}
                <Link href="/realestate/deals/tier2">
                  送信待ち Tier2（{tier2Count}件）
                </Link>
              </>
            ) : null}
            {tier2Summary.enabled ? (
              <span className="meta">
                {" "}
                · 本日送信 {tier2Summary.sent_today}/{tier2Summary.daily_cap}
              </span>
            ) : null}
          </p>
        </div>
      ) : null}

      <div className="card">
        <header>
          <span className="lvl">Jobs</span>
          <strong>候補の更新（Mac 常駐）</strong>
        </header>
        <p style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 8 }}>
          <EnqueueJobButton
            jobType="re_mail_match"
            title="物件メール候補を取り込む"
            label="メール候補を更新"
            payload={{ apply: true, days: 120, limit: 40 }}
          />
          <EnqueueJobButton
            jobType="re_deal_advice"
            title="案件にQ&A助言を付与"
            label="助言を更新"
            payload={{ apply: true }}
          />
          <EnqueueJobButton
            jobType="re_deal_inquiry_poll"
            title="第一問い合わせの返信を取込"
            label="返信取込"
            payload={{}}
          />
        </p>
      </div>

      {tab === "all" ? (
        <div className="card">
          <header>
            <span className="lvl">Funnel</span>
            <strong>件数</strong>
          </header>
          <p className="meta" style={{ marginTop: 8 }}>
            {FUNNEL.map((s) => (
              <span key={s} style={{ marginRight: 12 }}>
                {DEAL_STATUS_LABEL[s]} <strong>{counts[s] || 0}</strong>
              </span>
            ))}
            <span style={{ marginRight: 12 }}>
              見送り <strong>{counts.passed || 0}</strong>
            </span>
          </p>
        </div>
      ) : null}

      {tab === "all" ? (
        <>
          <div className="card">
            <header>
              <span className="lvl">Focus</span>
              <strong>今狙う条件（要約）</strong>
            </header>
            <ul className="meta" style={{ paddingLeft: 18, marginTop: 8 }}>
              {criteriaLines.length === 0 ? (
                <li>条件未取込</li>
              ) : (
                criteriaLines.slice(0, 6).map((c, i) => (
                  <li key={`${c.sort_order}-${i}`}>{c.raw_text}</li>
                ))
              )}
            </ul>
          </div>
          <div className="card">
            <header>
              <span className="lvl">運営経緯</span>
              <strong>809 ヒット（直近）</strong>
            </header>
            <ul className="meta" style={{ paddingLeft: 18, marginTop: 8 }}>
              {(ops || []).length === 0 ? (
                <li>まだ無し</li>
              ) : (
                (ops || []).map((e, i) => (
                  <li key={i}>
                    {(e.occurred_at || "").slice(0, 10)} · {e.subject}
                  </li>
                ))
              )}
            </ul>
          </div>
        </>
      ) : null}

      <div className="card">
        <header>
          <span className="lvl">Deals</span>
          <strong>
            案件一覧（{visibleDeals.length} 件
            {dedupeHiddenCount > 0
              ? ` · 重複 ${dedupeHiddenCount} 件を非表示`
              : ""}
            ）
          </strong>
        </header>
        {visibleDeals.length === 0 ? (
          <p className="meta" style={{ marginTop: 8 }}>
            該当案件がありません。「メール候補を更新」で取込してください。
          </p>
        ) : slimTable ? (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>評価スコア</th>
                  <th>状態</th>
                  <th>物件</th>
                  <th>エリア</th>
                  <th>価格</th>
                  <th>Grok評価</th>
                  <th>問合せ</th>
                  <th>最終動き</th>
                  <th>操作</th>
                  <th>詳細</th>
                </tr>
              </thead>
              <tbody>
                {visibleDeals.map((d) => {
                  const sj =
                    d.summary_json && typeof d.summary_json === "object"
                      ? (d.summary_json as Record<string, unknown>)
                      : {};
                  const grok =
                    sj.grok && typeof sj.grok === "object"
                      ? (sj.grok as Record<string, unknown>)
                      : null;
                  const inquiryStatus =
                    d.inquiry_status ||
                    (typeof sj.inquiry_status === "string"
                      ? sj.inquiry_status
                      : "none");
                  const evalInq = inquiryEval(d);
                  const fromRaw =
                    typeof sj.from === "string" ? sj.from : null;
                  const msgs = messagesByDeal.get(d.id) || [];
                  const evs = eventsByDeal.get(d.id) || [];
                  const activity = lastActivityLine(msgs, evs);
                  const dealOpenHref = openDealHref(d.id);
                  const band = scoreBand(d.match_score);
                  const hits = scoreHitsPreview(sj.hits);
                  const pursuing = pursueDeals.some((p) => p.id === d.id);
                  return (
                    <tr
                      key={d.id}
                      id={`deal-${d.id}`}
                      style={
                        highlightDeal === d.id
                          ? {
                              outline: "2px solid var(--danger, #b45309)",
                              outlineOffset: 2,
                            }
                          : pursuing
                            ? { background: "#f0fdf4" }
                            : undefined
                      }
                    >
                      <td>
                        <div style={scoreCellStyle(band)}>
                          {formatMatchScore(d.match_score)}
                          {band !== "none" ? (
                            <span className="meta" style={{ marginLeft: 6 }}>
                              {scoreBandLabel(band)}
                            </span>
                          ) : null}
                        </div>
                        {hits ? (
                          <div className="meta" style={{ fontSize: 11 }}>
                            {hits}
                          </div>
                        ) : null}
                        {pursuing ? (
                          <div
                            className="meta"
                            style={{ color: "#047857", fontSize: 11 }}
                          >
                            買い進め中
                          </div>
                        ) : null}
                      </td>
                      <td>{DEAL_STATUS_LABEL[d.status] || d.status}</td>
                      <td>
                        {d.title}
                        {evalInq.badges.length > 0 ? (
                          <div className="meta">
                            {evalInq.badges.map((b) => (
                              <span
                                key={b}
                                style={{
                                  display: "inline-block",
                                  marginRight: 4,
                                  padding: "1px 6px",
                                  borderRadius: 4,
                                  fontSize: 11,
                                  background:
                                    b === "再検討" ? "#fef3c7" : "#eff6ff",
                                }}
                              >
                                {b}
                              </span>
                            ))}
                          </div>
                        ) : null}
                        <div className="meta">
                          {SOURCE_BADGE[d.source] || d.source}
                        </div>
                      </td>
                      <td className="meta">{d.area || "—"}</td>
                      <td className="meta">
                        {d.price_man != null
                          ? fmtYen(Number(d.price_man) * 10000)
                          : "—"}
                      </td>
                      <td className="meta">{grokOneLine(grok)}</td>
                      <td>
                        <span style={inquiryChipStyle(inquiryStatus)}>
                          {INQUIRY_STATUS_LABEL[inquiryStatus] ||
                            inquiryStatus}
                        </span>
                      </td>
                      <td className="meta">
                        {activity.at
                          ? `${activity.at.slice(0, 10)} ${activity.text.slice(0, 32)}`
                          : "—"}
                      </td>
                      <td>
                        <DealReviewActions
                          dealId={d.id}
                          status={d.status}
                          gmailId={
                            typeof sj.gmail_id === "string"
                              ? sj.gmail_id
                              : null
                          }
                          gmailReadAt={
                            typeof sj.gmail_read_at === "string"
                              ? sj.gmail_read_at
                              : null
                          }
                          dealTitle={d.title}
                          fromRaw={fromRaw}
                          inquiryReady={evalInq.tier1}
                          inquiryHasTo={evalInq.hasTo}
                          inquiryBadges={evalInq.badges}
                          inquiryChannel={evalInq.inquiryChannel}
                          openDealHref={dealOpenHref}
                        />
                      </td>
                      <td>
                        <Link href={dealOpenHref} className="btn">
                          開く
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>状態</th>
                  <th>評価スコア</th>
                  <th>タイトル</th>
                  <th>エリア</th>
                  <th>価格</th>
                  <th>問合せ</th>
                  <th>操作</th>
                  <th>詳細</th>
                </tr>
              </thead>
              <tbody>
                {visibleDeals.map((d) => {
                  const sj =
                    d.summary_json && typeof d.summary_json === "object"
                      ? (d.summary_json as Record<string, unknown>)
                      : {};
                  const inquiryStatus =
                    d.inquiry_status ||
                    (typeof sj.inquiry_status === "string"
                      ? sj.inquiry_status
                      : "none");
                  const band = scoreBand(d.match_score);
                  const hits = scoreHitsPreview(sj.hits);
                  const pursuing = pursueDeals.some((p) => p.id === d.id);
                  return (
                    <tr
                      key={d.id}
                      style={
                        pursuing ? { background: "#f0fdf4" } : undefined
                      }
                    >
                      <td>
                        {DEAL_STATUS_LABEL[d.status] || d.status}
                        {pursuing ? (
                          <div
                            className="meta"
                            style={{ color: "#047857", fontSize: 11 }}
                          >
                            買い進め中
                          </div>
                        ) : null}
                      </td>
                      <td>
                        <div style={scoreCellStyle(band)}>
                          {formatMatchScore(d.match_score)}
                          {band !== "none" ? (
                            <span className="meta" style={{ marginLeft: 6 }}>
                              {scoreBandLabel(band)}
                            </span>
                          ) : null}
                        </div>
                        {hits ? (
                          <div className="meta" style={{ fontSize: 11 }}>
                            {hits}
                          </div>
                        ) : null}
                      </td>
                      <td>
                        {d.title}
                        <div className="meta">{d.source}</div>
                      </td>
                      <td className="meta">{d.area || "—"}</td>
                      <td className="meta">
                        {d.price_man != null
                          ? fmtYen(Number(d.price_man) * 10000)
                          : "—"}
                      </td>
                      <td>
                        <span style={inquiryChipStyle(inquiryStatus)}>
                          {INQUIRY_STATUS_LABEL[inquiryStatus] ||
                            inquiryStatus}
                        </span>
                      </td>
                      <td>
                        <DealReviewActions
                          dealId={d.id}
                          status={d.status}
                          gmailId={
                            typeof sj.gmail_id === "string"
                              ? sj.gmail_id
                              : null
                          }
                          gmailReadAt={
                            typeof sj.gmail_read_at === "string"
                              ? sj.gmail_read_at
                              : null
                          }
                        />
                      </td>
                      <td>
                        <Link href={openDealHref(d.id)} className="btn">
                          開く
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Suspense fallback={null}>
        <DealsDrawerHost dealId={highlightDeal || null} />
      </Suspense>
    </Shell>
  );
}
