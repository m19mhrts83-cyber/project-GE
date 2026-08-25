"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import DealReviewActions from "@/components/DealReviewActions";
import {
  DEALS_PAGE_SIZE,
  filterDealsByTitle,
  pageForDealId,
  paginateDeals,
} from "@/lib/reDealsListUi";
import { INQUIRY_STATUS_LABEL } from "@/lib/rePipelineUi";
import {
  scoreBandLabel,
  scoreCellStyle,
  type ScoreBand,
} from "@/lib/reDealScoreUi";
import type { InquiryChannel } from "@/lib/reInquiryChannel";

export type DealsListRow = {
  id: string;
  title: string;
  status: string;
  statusLabel: string;
  sourceBadge: string;
  area: string;
  priceLabel: string;
  grokLine: string;
  inquiryStatus: string;
  activityLine: string;
  scoreLabel: string;
  scoreBand: ScoreBand;
  hitsPreview: string;
  pursuing: boolean;
  highlighted: boolean;
  badges: string[];
  openHref: string;
  review: {
    gmailId: string | null;
    gmailReadAt: string | null;
    fromRaw: string | null;
    inquiryReady: boolean;
    inquiryHasTo: boolean;
    inquiryBadges: string[];
    inquiryChannel: InquiryChannel | null;
  };
};

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

function ScoreCell({
  row,
  showPursue,
}: {
  row: DealsListRow;
  showPursue?: boolean;
}) {
  return (
    <td>
      <div style={scoreCellStyle(row.scoreBand)}>
        {row.scoreLabel}
        {row.scoreBand !== "none" ? (
          <span className="meta" style={{ marginLeft: 6 }}>
            {scoreBandLabel(row.scoreBand)}
          </span>
        ) : null}
      </div>
      {row.hitsPreview ? (
        <div className="meta" style={{ fontSize: 11 }}>
          {row.hitsPreview}
        </div>
      ) : null}
      {showPursue && row.pursuing ? (
        <div className="meta" style={{ color: "#047857", fontSize: 11 }}>
          買い進め中
        </div>
      ) : null}
    </td>
  );
}

function TitleCell({ row, showBadges }: { row: DealsListRow; showBadges: boolean }) {
  return (
    <td className="deals-title-cell">
      <span className="deals-title-text" title={row.title}>
        {row.title}
      </span>
      {showBadges && row.badges.length > 0 ? (
        <div className="meta">
          {row.badges.map((b) => (
            <span
              key={b}
              style={{
                display: "inline-block",
                marginRight: 4,
                padding: "1px 6px",
                borderRadius: 4,
                fontSize: 11,
                background: b === "再検討" ? "#fef3c7" : "#eff6ff",
              }}
            >
              {b}
            </span>
          ))}
        </div>
      ) : null}
      <div className="meta">{row.sourceBadge}</div>
    </td>
  );
}

function OpenCell({ href }: { href: string }) {
  return (
    <td className="deals-col-open">
      <Link href={href} className="btn">
        開く
      </Link>
    </td>
  );
}

export default function DealsListTable({
  variant,
  rows,
  dedupeHiddenCount,
}: {
  variant: "slim" | "full";
  rows: DealsListRow[];
  dedupeHiddenCount: number;
}) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(() =>
    pageForDealId(
      rows,
      rows.find((r) => r.highlighted)?.id
    )
  );

  const filtered = useMemo(
    () => filterDealsByTitle(rows, query),
    [rows, query]
  );
  const paged = useMemo(
    () => paginateDeals(filtered, page, DEALS_PAGE_SIZE),
    [filtered, page]
  );

  function onQueryChange(next: string) {
    setQuery(next);
    setPage(1);
  }

  return (
    <div className="card deals-list">
      <header>
        <span className="lvl">Deals</span>
        <strong>
          案件一覧（{rows.length} 件
          {dedupeHiddenCount > 0
            ? ` · 重複 ${dedupeHiddenCount} 件を非表示`
            : ""}
          ）
        </strong>
      </header>
      {rows.length === 0 ? (
        <p className="meta" style={{ marginTop: 8 }}>
          該当案件がありません。「メール候補を更新」で取込してください。
        </p>
      ) : (
        <>
          <div className="deals-list-toolbar">
            <label className="deals-list-search">
              <span className="meta">件名で検索</span>
              <input
                type="search"
                value={query}
                onChange={(e) => onQueryChange(e.target.value)}
                placeholder="物件名・件名の一部"
                aria-label="件名で検索"
              />
            </label>
            <p className="meta" style={{ margin: 0 }}>
              {filtered.length === 0
                ? "該当なし"
                : `${filtered.length} 件中 ${paged.from}–${paged.to} 件`}
            </p>
          </div>
          {filtered.length === 0 ? (
            <p className="meta">この件名に一致する案件はありません。</p>
          ) : (
            <>
              <div className="deals-list-scroll">
                <table className="deals-list-table">
                  <thead>
                    {variant === "slim" ? (
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
                        <th className="deals-col-open">詳細</th>
                      </tr>
                    ) : (
                      <tr>
                        <th>状態</th>
                        <th>評価スコア</th>
                        <th>タイトル</th>
                        <th>エリア</th>
                        <th>価格</th>
                        <th>問合せ</th>
                        <th>操作</th>
                        <th className="deals-col-open">詳細</th>
                      </tr>
                    )}
                  </thead>
                  <tbody>
                    {paged.slice.map((d) => {
                      const rowClass = [
                        d.pursuing ? "deals-row-pursue" : "",
                        d.highlighted ? "deals-row-highlight" : "",
                      ]
                        .filter(Boolean)
                        .join(" ");
                      return (
                        <tr
                          key={d.id}
                          id={`deal-${d.id}`}
                          className={rowClass || undefined}
                        >
                          {variant === "slim" ? (
                            <>
                              <ScoreCell row={d} showPursue />
                              <td>{d.statusLabel}</td>
                              <TitleCell row={d} showBadges />
                              <td className="meta">{d.area}</td>
                              <td className="meta">{d.priceLabel}</td>
                              <td className="meta deals-clip" title={d.grokLine}>
                                {d.grokLine}
                              </td>
                              <td>
                                <span style={inquiryChipStyle(d.inquiryStatus)}>
                                  {INQUIRY_STATUS_LABEL[d.inquiryStatus] ||
                                    d.inquiryStatus}
                                </span>
                              </td>
                              <td className="meta deals-clip" title={d.activityLine}>
                                {d.activityLine}
                              </td>
                              <td>
                                <DealReviewActions
                                  dealId={d.id}
                                  status={d.status}
                                  gmailId={d.review.gmailId}
                                  gmailReadAt={d.review.gmailReadAt}
                                  dealTitle={d.title}
                                  fromRaw={d.review.fromRaw}
                                  inquiryReady={d.review.inquiryReady}
                                  inquiryHasTo={d.review.inquiryHasTo}
                                  inquiryBadges={d.review.inquiryBadges}
                                  inquiryChannel={d.review.inquiryChannel}
                                  openDealHref={d.openHref}
                                />
                              </td>
                              <OpenCell href={d.openHref} />
                            </>
                          ) : (
                            <>
                              <td>
                                {d.statusLabel}
                                {d.pursuing ? (
                                  <div
                                    className="meta"
                                    style={{ color: "#047857", fontSize: 11 }}
                                  >
                                    買い進め中
                                  </div>
                                ) : null}
                              </td>
                              <ScoreCell row={d} />
                              <TitleCell row={d} showBadges={false} />
                              <td className="meta">{d.area}</td>
                              <td className="meta">{d.priceLabel}</td>
                              <td>
                                <span style={inquiryChipStyle(d.inquiryStatus)}>
                                  {INQUIRY_STATUS_LABEL[d.inquiryStatus] ||
                                    d.inquiryStatus}
                                </span>
                              </td>
                              <td>
                                <DealReviewActions
                                  dealId={d.id}
                                  status={d.status}
                                  gmailId={d.review.gmailId}
                                  gmailReadAt={d.review.gmailReadAt}
                                />
                              </td>
                              <OpenCell href={d.openHref} />
                            </>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {paged.pageCount > 1 ? (
                <div className="deals-list-pager">
                  <button
                    type="button"
                    className="btn"
                    disabled={paged.page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    前へ
                  </button>
                  <span className="meta">
                    {paged.page} / {paged.pageCount} ページ
                  </span>
                  <button
                    type="button"
                    className="btn"
                    disabled={paged.page >= paged.pageCount}
                    onClick={() =>
                      setPage((p) => Math.min(paged.pageCount, p + 1))
                    }
                  >
                    次へ
                  </button>
                </div>
              ) : null}
            </>
          )}
        </>
      )}
    </div>
  );
}
