"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import { generateQuietEdgeMonthlyReview } from "@/app/actions/quietEdge";

export type MonthlyReview = {
  period_key: string;
  title: string;
  body: string;
  created_at: string;
};

export default function QuietEdgeMonthlyReview({
  initial,
  currentYm,
}: {
  initial: MonthlyReview | null;
  currentYm: string;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [review, setReview] = useState<MonthlyReview | null>(initial);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setReview(initial);
  }, [initial]);

  return (
    <section className="card qe-monthly-review">
      <header>
        <span className="lvl">月次</span>
        <strong>{currentYm} の分析レビュー</strong>
      </header>
      <p className="meta">
        毎日聞かず、月単位でいびき・Journal（夜の防衛線）・前月比較をまとめます。
        診断ではありません。観察の主線はこちらです。
      </p>
      <div className="qe-form-actions">
        <button
          type="button"
          className="btn"
          disabled={pending}
          onClick={() => {
            setErr(null);
            start(async () => {
              const r = await generateQuietEdgeMonthlyReview(currentYm);
              if (!r.ok) {
                setErr(r.error);
                return;
              }
              setReview({
                period_key: r.period || currentYm,
                title: `${r.period || currentYm} 月次レビュー`,
                body: r.text,
                created_at: r.created_at || new Date().toISOString(),
              });
              router.refresh();
            });
          }}
        >
          {pending
            ? "月次レビュー作成中…"
            : review
              ? "月次レビューを更新"
              : "月次レビューを作成"}
        </button>
      </div>
      {err ? <p className="qe-err">{err}</p> : null}
      {review ? (
        <>
          <p className="meta">
            {review.title} ／{" "}
            {new Date(review.created_at).toLocaleString("ja-JP", {
              timeZone: "Asia/Tokyo",
            })}
          </p>
          <pre className="qe-review-text qe-review-text-monthly">{review.body}</pre>
        </>
      ) : (
        <p className="sum">
          まだ月次レビューがありません。月末や気になったタイミングで作成してください。
        </p>
      )}
    </section>
  );
}
