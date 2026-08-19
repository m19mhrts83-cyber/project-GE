function yearList(now: number): number[] {
  const from = now - 12;
  const out: number[] = [];
  for (let y = from; y <= now; y += 1) out.push(y);
  return out;
}

export default function HouseholdBsYearNav({
  year,
  live,
}: {
  year: string;
  live?: boolean;
}) {
  const now = new Date().getFullYear();
  const y = Number(year);
  const years = yearList(now);
  const liveQ = live ? "&live=1" : "";
  const href = (n: number) => `/household-bs?year=${n}${liveQ}`;
  const prev = y - 1;
  const next = y + 1;
  const canPrev = prev >= years[0];
  const canNext = next <= now;

  return (
    <div className="card" style={{ marginTop: 12 }}>
      <header>
        <span className="lvl">年度</span>
        <strong>{y}年</strong>
      </header>
      <div className="year-nav" style={{ marginTop: 8 }}>
        {canPrev ? (
          <a className="year-nav-step" href={href(prev)}>
            ‹ {prev}
          </a>
        ) : (
          <span className="year-nav-step is-disabled">‹</span>
        )}
        <span className="year-nav-current">{y}</span>
        {canNext ? (
          <a className="year-nav-step" href={href(next)}>
            {next} ›
          </a>
        ) : (
          <span className="year-nav-step is-disabled">›</span>
        )}
      </div>
      <div className="year-nav-scroll" role="navigation" aria-label="年度一覧">
        {years.map((n) => (
          <a
            key={n}
            className={`year-chip${n === y ? " is-active" : ""}`}
            href={href(n)}
          >
            {n}
          </a>
        ))}
      </div>
    </div>
  );
}
