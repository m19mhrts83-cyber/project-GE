import Link from "next/link";
import {
  LENS_META,
  sleepSnippet,
  type PerformanceJournalRow,
  type PerformanceLens,
} from "@/lib/performance";

export default function PerformanceJournalBand({
  lens,
  rows,
}: {
  lens: PerformanceLens;
  rows: PerformanceJournalRow[];
}) {
  const meta = LENS_META[lens];

  return (
    <section className="card">
      <header>
        <span className="lvl">Journal</span>
        <strong>{meta.title}レンズ（直近）</strong>
      </header>
      <p className="meta">
        Quiet Edge と同じ ★Journal 投影（`vital_journal_daily`）を用途別に絞っています。
      </p>
      {!rows.length ? (
        <p className="sum">{meta.empty}</p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: "0.5rem 0" }}>
          {rows.map((r) => (
            <li
              key={r.recorded_at}
              style={{
                padding: "0.55rem 0",
                borderBottom: "1px solid var(--line, #ddd)",
              }}
            >
              <strong>{r.recorded_at}</strong>
              <p className="sum" style={{ margin: "0.25rem 0 0" }}>
                {sleepSnippet(r.excerpt, r.sleep_signal) ||
                  (r.excerpt || "").slice(0, 160)}
                {(r.excerpt || "").length > 160 ? "…" : ""}
              </p>
            </li>
          ))}
        </ul>
      )}
      <p className="meta">
        いびき治療の経過は{" "}
        <Link href="/quiet-edge">Quiet Edge</Link>
        ／もう一方のパフォーマンスは{" "}
        <Link href={lens === "work" ? "/performance/move" : "/performance/work"}>
          {lens === "work" ? "運動" : "仕事"}
        </Link>
      </p>
    </section>
  );
}
