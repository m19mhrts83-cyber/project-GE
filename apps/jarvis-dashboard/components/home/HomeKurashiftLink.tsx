import { KURASHIFT_URL } from "@/lib/nav";

/** 別アプリへの入口。ダッシュボード内に /trade は置かない */
export default function HomeKurashiftLink() {
  return (
    <article className="card" style={{ marginBottom: 16 }}>
      <header>
        <span className="lvl">お金</span>
        <strong>KURASHIFT</strong>
      </header>
      <p className="sum" style={{ margin: "6px 0 12px" }}>
        クラシフト（暮らし・資産HQ）はダッシュボードとは別アプリです。
      </p>
      <a
        className="btn primary"
        href={KURASHIFT_URL}
        target="_blank"
        rel="noopener noreferrer"
      >
        KURASHIFT を開く ↗
      </a>
    </article>
  );
}
