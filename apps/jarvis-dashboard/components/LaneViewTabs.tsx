import {
  VIEW_LABEL,
  laneViewHref,
  type LaneView,
} from "@/lib/laneView";

type Stat = { view: LaneView; count: number };

/**
 * 通常の <a> でハード遷移する（クライアント router 非依存）。
 * クエリだけの Soft Nav や button onClick が効かない端末向け。
 */
export default function LaneViewTabs({
  basePath,
  current,
  stats,
}: {
  basePath: string;
  current: LaneView;
  stats: Stat[];
}) {
  return (
    <>
      <p className="meta" style={{ marginTop: -8, marginBottom: 12 }}>
        上の数字をタップすると、その一覧だけ表示します（いま: {VIEW_LABEL[current]}
        ）。URL が{" "}
        <code style={{ fontSize: "0.85em" }}>
          {laneViewHref(basePath, current)}
        </code>{" "}
        に変わります。
      </p>
      <div className="stats" role="navigation" aria-label="表示の切り替え">
        {stats.map((s) => {
          const href = laneViewHref(basePath, s.view);
          const on = current === s.view;
          return (
            <a
              key={s.view}
              href={href}
              className={`stat stat-link${on ? " on" : ""}`}
              aria-current={on ? "page" : undefined}
            >
              {VIEW_LABEL[s.view]} <strong>{s.count}</strong>
            </a>
          );
        })}
      </div>
    </>
  );
}
