"use client";

import { useState, useTransition } from "react";
import { generateQuietEdgeReview } from "@/app/actions/quietEdge";

export default function QuietEdgeReviewPanel() {
  const [pending, start] = useTransition();
  const [text, setText] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  return (
    <section className="card qe-review-panel">
      <header>
        <span className="lvl">Review</span>
        <strong>観察レビュー（Journal＋補完）</strong>
      </header>
      <p className="meta">
        診断ではなく、医師に見せる前の観察整理です。いびき・Health・Journal・補完メモを横断します。
      </p>
      <div className="qe-form-actions">
        <button
          type="button"
          className="btn"
          disabled={pending}
          onClick={() => {
            setErr(null);
            start(async () => {
              const r = await generateQuietEdgeReview();
              if (!r.ok) {
                setErr(r.error);
                setText(null);
                return;
              }
              setText(r.text);
            });
          }}
        >
          {pending ? "生成中…" : "レビューを生成"}
        </button>
      </div>
      {err ? <p className="qe-err">{err}</p> : null}
      {text ? <pre className="qe-review-text">{text}</pre> : null}
    </section>
  );
}
