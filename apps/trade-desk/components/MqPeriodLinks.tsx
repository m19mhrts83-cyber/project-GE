import type { GrainFilter } from "@/lib/mqAggregate";

export default function MqPeriodLinks({
  grain,
  periods,
  current,
  makeHref,
}: {
  grain: GrainFilter;
  periods: string[];
  current: string;
  makeHref: (v: string) => string;
}) {
  if (periods.length === 0) {
    return <span className="meta">（保存後に選択可）</span>;
  }

  if (grain === "year") {
    const y = Number(current.slice(0, 4));
    const nums = periods.map((p) => Number(p.slice(0, 4)));
    const min = Math.min(...nums);
    const max = Math.max(...nums);
    const prev = y - 1;
    const next = y + 1;
    const canPrev = prev >= min;
    const canNext = next <= max;

    return (
      <div className="mq-period-nav">
        <div className="year-nav">
          {canPrev ? (
            <a className="year-nav-step" href={makeHref(String(prev))}>
              ‹ {prev}
            </a>
          ) : (
            <span className="year-nav-step is-disabled">‹</span>
          )}
          <span className="year-nav-current">{y}</span>
          {canNext ? (
            <a className="year-nav-step" href={makeHref(String(next))}>
              {next} ›
            </a>
          ) : (
            <span className="year-nav-step is-disabled">›</span>
          )}
        </div>
        <div className="year-nav-scroll" role="navigation">
          {periods.map((v) => {
            const n = v.slice(0, 4);
            return (
              <a
                key={v}
                className={`year-chip${n === String(y) ? " is-active" : ""}`}
                href={makeHref(v)}
              >
                {n}
              </a>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div className="year-nav-scroll" role="navigation">
      {periods.map((v) => (
        <a
          key={v}
          className={`year-chip${current === v ? " is-active" : ""}`}
          href={makeHref(v)}
        >
          {v}
        </a>
      ))}
    </div>
  );
}
