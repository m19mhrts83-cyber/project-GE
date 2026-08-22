"use client";

import { useMemo, useState, useTransition } from "react";
import { applyZaimCategory } from "@/app/actions/zaimWatch";
import {
  matchCategoryValue,
  zaimCategoryGroups,
  type ZaimCategoryReviewItem,
} from "@/lib/zaimCategoryCatalog";

function fmtYen(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${Math.round(n).toLocaleString("ja-JP")}円`;
}

export default function ZaimCategoryPicker({
  item,
  path = "/zaim",
  variant = "review",
  fixId,
}: {
  item: ZaimCategoryReviewItem;
  path?: string;
  variant?: "review" | "fix";
  fixId?: string;
}) {
  const groups = useMemo(() => zaimCategoryGroups(), []);
  const initialCategory =
    matchCategoryValue(item.pending_category) ||
    matchCategoryValue(item.suggest) ||
    "";
  const [category, setCategory] = useState(initialCategory);
  const [genre, setGenre] = useState(item.pending_genre || item.suggest_genre || "");
  const [pending, start] = useTransition();
  const [error, setError] = useState("");
  const [done, setDone] = useState(Boolean(item.pending_apply));

  const selected = groups
    .flatMap((g) => g.items)
    .find((c) => c.value === category);
  const genres = selected?.genres || [];
  const showGenre = genres.length > 0;

  const canApply = Boolean(category) && !done && !pending;

  return (
    <div className="zaim-category-picker">
      <div className="zaim-category-picker-meta">
        {item.date ? <span className="watch-action-date">{item.date}</span> : null}
        <span className="watch-action-shop">{item.shop || "—"}</span>
        {item.amount != null ? (
          <span className="watch-action-yen">{fmtYen(item.amount)}</span>
        ) : null}
      </div>
      <p className="zaim-category-current">
        現在: {item.category || "—"}
        {item.suggest ? (
          <span className="zaim-category-suggest">
            {" "}
            → 提案: {item.suggest}
            {item.confidence ? `（${item.confidence}）` : ""}
          </span>
        ) : null}
      </p>
      {done ? (
        <p className="meta zaim-category-pending">
          反映待ち: {item.pending_category || category}
          {item.pending_genre || genre ? ` / ${item.pending_genre || genre}` : ""}
        </p>
      ) : (
        <div className="zaim-category-controls">
          <label className="zaim-category-field">
            <span>大分類</span>
            <select
              value={category}
              onChange={(e) => {
                setCategory(e.target.value);
                setGenre("");
                setError("");
              }}
              disabled={pending}
            >
              <option value="">選択…</option>
              {groups.map((g) => (
                <optgroup key={g.group} label={g.group}>
                  {g.items.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          {showGenre ? (
            <label className="zaim-category-field">
              <span>内訳</span>
              <select
                value={genre}
                onChange={(e) => {
                  setGenre(e.target.value);
                  setError("");
                }}
                disabled={pending || !category}
              >
                <option value="">（なし）</option>
                {genres.map((g) => (
                  <option key={g} value={g}>
                    {g}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <button
            type="button"
            className="btn zaim-category-apply"
            disabled={!canApply}
            onClick={() =>
              start(async () => {
                setError("");
                const rowKey = (item.row_key || "").trim();
                if (!rowKey) {
                  setError("row_key がありません");
                  return;
                }
                const res = await applyZaimCategory(
                  {
                    rowKey,
                    category,
                    genre: showGenre ? genre : "",
                    source: variant === "fix" ? "recent_fix" : "category_review",
                    fixId: fixId || undefined,
                    item,
                  },
                  path,
                );
                if (res.ok) {
                  setDone(true);
                } else {
                  setError(res.error || "反映に失敗しました");
                }
              })
            }
          >
            {pending ? "送信中…" : "反映"}
          </button>
        </div>
      )}
      {error ? <p className="meta zaim-category-error">{error}</p> : null}
    </div>
  );
}
