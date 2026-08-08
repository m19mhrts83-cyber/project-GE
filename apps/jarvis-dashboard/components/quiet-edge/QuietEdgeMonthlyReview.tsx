"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import {
  generateQuietEdgeMonthlyReview,
  loadLatestMonthlyReview,
} from "@/app/actions/quietEdge";
import {
  defaultMonthlyReviewYm,
  monthKeyJst,
  shiftMonthYm,
} from "@/lib/quietEdgeContext";

export type MonthlyReview = {
  period_key: string;
  title: string;
  body: string;
  created_at: string;
};

export default function QuietEdgeMonthlyReview({
  initial,
  initialYm,
}: {
  initial: MonthlyReview | null;
  /** 既定は先月（JST）。例: 今日が 2026-08-08 → 2026-07 */
  initialYm?: string;
}) {
  const router = useRouter();
  const thisYm = monthKeyJst();
  const lastYm = defaultMonthlyReviewYm();
  const [ym, setYm] = useState(initialYm || lastYm);
  const [pending, start] = useTransition();
  const [loadingMonth, setLoadingMonth] = useState(false);
  const [review, setReview] = useState<MonthlyReview | null>(initial);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setYm(initialYm || lastYm);
    setReview(initial);
  }, [initial, initialYm, lastYm]);

  function selectYm(next: string) {
    if (!/^\d{4}-\d{2}$/.test(next) || next === ym) return;
    setYm(next);
    setErr(null);
    setLoadingMonth(true);
    start(async () => {
      try {
        const row = await loadLatestMonthlyReview(next);
        setReview(
          row
            ? {
                period_key: row.period_key,
                title: row.title,
                body: row.body,
                created_at: row.created_at,
              }
            : null,
        );
      } catch (e) {
        setErr(e instanceof Error ? e.message : "月次レビューの読込に失敗");
        setReview(null);
      } finally {
        setLoadingMonth(false);
      }
    });
  }

  return (
    <section className="card qe-monthly-review">
      <header>
        <span className="lvl">月次</span>
        <strong>{ym} の分析レビュー</strong>
      </header>
      <p className="meta">
        既定は先月（{lastYm}）。いびき・Journal（夜の防衛線）とその前月比較をまとめます。
        診断ではありません。観察の主線はこちらです。
      </p>
      <div className="qe-month-nav" role="group" aria-label="レビュー対象月">
        <button
          type="button"
          className="btn qe-month-nav-btn"
          disabled={pending || loadingMonth}
          onClick={() => selectYm(shiftMonthYm(ym, -1))}
        >
          ← 前の月
        </button>
        <button
          type="button"
          className={`btn qe-month-nav-btn${ym === lastYm ? " qe-month-nav-active" : ""}`}
          disabled={pending || loadingMonth}
          onClick={() => selectYm(lastYm)}
        >
          先月
        </button>
        <button
          type="button"
          className={`btn qe-month-nav-btn${ym === thisYm ? " qe-month-nav-active" : ""}`}
          disabled={pending || loadingMonth}
          onClick={() => selectYm(thisYm)}
        >
          今月
        </button>
        <button
          type="button"
          className="btn qe-month-nav-btn"
          disabled={pending || loadingMonth || ym >= thisYm}
          onClick={() => selectYm(shiftMonthYm(ym, 1))}
        >
          次の月 →
        </button>
      </div>
      <div className="qe-form-actions">
        <button
          type="button"
          className="btn"
          disabled={pending || loadingMonth}
          onClick={() => {
            setErr(null);
            start(async () => {
              const r = await generateQuietEdgeMonthlyReview(ym);
              if (!r.ok) {
                setErr(r.error);
                return;
              }
              setReview({
                period_key: r.period || ym,
                title: `${r.period || ym} の分析レビュー`,
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
              ? `${ym} のレビューを更新`
              : `${ym} のレビューを作成`}
        </button>
      </div>
      {err ? <p className="qe-err">{err}</p> : null}
      {loadingMonth ? <p className="meta">読込中…</p> : null}
      {review ? (
        <>
          <p className="meta">
            {review.title || `${review.period_key} の分析レビュー`} ／{" "}
            {new Date(review.created_at).toLocaleString("ja-JP", {
              timeZone: "Asia/Tokyo",
            })}
          </p>
          <pre className="qe-review-text qe-review-text-monthly">{review.body}</pre>
        </>
      ) : !loadingMonth ? (
        <p className="sum">
          {ym} の月次レビューはまだありません。作成すると前月比較付きで表示されます。
        </p>
      ) : null}
    </section>
  );
}
