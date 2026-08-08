"use client";

import { useEffect, useState } from "react";

export type LatestIngestReview = {
  period_key: string;
  title: string;
  body: string;
  created_at: string;
};

export type IngestReviewEvent =
  | LatestIngestReview
  | { pending: true };

const EVENT = "qe-ingest-review";

function isPendingEvent(
  detail: IngestReviewEvent | null | undefined,
): detail is { pending: true } {
  return Boolean(detail && "pending" in detail && detail.pending === true);
}

export function dispatchIngestReview(review: IngestReviewEvent) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<IngestReviewEvent>(EVENT, { detail: review }));
}

/** 画面最上段: 直近の取込レビュー */
export default function QuietEdgeLatestReview({
  initial,
}: {
  initial: LatestIngestReview | null;
}) {
  const [review, setReview] = useState<LatestIngestReview | null>(initial);
  const [pendingHint, setPendingHint] = useState(false);

  useEffect(() => {
    setReview(initial);
  }, [initial]);

  useEffect(() => {
    function onReview(e: Event) {
      const ce = e as CustomEvent<IngestReviewEvent>;
      if (isPendingEvent(ce.detail)) {
        setPendingHint(true);
        return;
      }
      if (ce.detail && "body" in ce.detail) {
        setPendingHint(false);
        setReview(ce.detail);
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    }
    window.addEventListener(EVENT, onReview);
    return () => window.removeEventListener(EVENT, onReview);
  }, []);

  return (
    <article className="card qe-latest-review">
      <header>
        <span className="lvl">直近レビュー</span>
        <strong>
          {review
            ? review.title || `取込レビュー ${review.period_key}`
            : "取込レビュー"}
        </strong>
      </header>
      {pendingHint ? (
        <p className="meta">取り込み後のレビューを作成中…</p>
      ) : null}
      {review ? (
        <>
          <p className="meta">
            {review.period_key} ／{" "}
            {new Date(review.created_at).toLocaleString("ja-JP", {
              timeZone: "Asia/Tokyo",
            })}
          </p>
          <pre className="qe-review-text qe-review-text-hero">{review.body}</pre>
        </>
      ) : (
        <p className="sum">
          AutoSnore を取り込むと、ここに直近の Gemini レビューが出ます（診断ではなく観察メモ）。
        </p>
      )}
    </article>
  );
}
