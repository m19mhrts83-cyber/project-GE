import { TRADE_DESK_URL } from "@/lib/nav";

/** 別アプリへの入口。ダッシュボード内に /trade は置かない */
export default function HomeTradeDeskLink() {
  return (
    <article className="card" style={{ marginBottom: 16 }}>
      <header>
        <span className="lvl">お金</span>
        <strong>Trade Desk</strong>
      </header>
      <p className="sum" style={{ margin: "6px 0 12px" }}>
        株・資産デスクはダッシュボードとは別アプリです。
      </p>
      <a
        className="btn primary"
        href={TRADE_DESK_URL}
        target="_blank"
        rel="noopener noreferrer"
      >
        Trade Desk を開く ↗
      </a>
    </article>
  );
}
