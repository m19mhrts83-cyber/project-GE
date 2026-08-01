"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

export type LaneView = "unread" | "sent" | "skipped" | "snoozed" | "activity";

const VIEW_LABEL: Record<LaneView, string> = {
  unread: "未読",
  sent: "送信済み",
  skipped: "スキップ",
  snoozed: "後で",
  activity: "活動概要",
};

type Stat = { view: LaneView; count: number };

/** クエリ遷移＋明示 refresh（iPhone で同一パスの searchParams が効かない対策） */
export default function LaneViewTabs({
  basePath,
  current,
  stats,
}: {
  basePath: string;
  current: LaneView;
  stats: Stat[];
}) {
  const router = useRouter();
  const [pending, start] = useTransition();

  function go(view: LaneView) {
    const href =
      view === "unread" ? `${basePath}?view=unread` : `${basePath}?view=${view}`;
    start(() => {
      router.push(href);
      router.refresh();
    });
    // Soft nav が効かない端末向けに、少し待って URL が変わっていなければフル遷移
    window.setTimeout(() => {
      try {
        const u = new URL(window.location.href);
        const now = (u.searchParams.get("view") || "unread") as LaneView;
        if (now !== view) {
          window.location.assign(href);
        }
      } catch {
        window.location.assign(href);
      }
    }, 400);
  }

  return (
    <>
      <p className="meta" style={{ marginTop: -8, marginBottom: 12 }}>
        上の数字をタップすると、その一覧だけ表示します（いま: {VIEW_LABEL[current]}
        ）{pending ? " …切替中" : ""}。
      </p>
      <div className="stats" role="tablist" aria-label="表示の切り替え">
        {stats.map((s) => (
          <button
            key={s.view}
            type="button"
            role="tab"
            aria-selected={current === s.view}
            className={`stat stat-link${current === s.view ? " on" : ""}`}
            disabled={pending}
            onClick={() => go(s.view)}
          >
            {VIEW_LABEL[s.view]} <strong>{s.count}</strong>
          </button>
        ))}
      </div>
    </>
  );
}

export { VIEW_LABEL };
