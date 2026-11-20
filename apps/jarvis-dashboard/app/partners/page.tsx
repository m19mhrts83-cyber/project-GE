import Link from "next/link";
import Shell from "@/components/Shell";
import { CHANNEL_LABEL, clip, cleanBody, jstStamp } from "@/lib/commHistory";
import { loadPartySummaries } from "@/lib/commHistoryServer";

export const dynamic = "force-dynamic";
export const metadata = { title: "パートナーのやり取り｜Jarvis" };

export default async function PartnersPage() {
  const r = await loadPartySummaries({ perParty: 3 });
  return (
    <Shell active="/partners">
      <h1>パートナーのやり取り</h1>
      <p className="sub">
        コミュニケーション台帳から、相手ごとの直近のやり取りを最後にやり取りした順に並べています。メール・Chatwork・LINE をまとめて見られます。
        返信は判断デスクで声で頼むと、ここと同じ履歴を踏まえた下書きが作られます。
      </p>
      {!r.ok ? <p className="empty">読み込みに失敗: {r.error}</p> : null}
      {r.ok && r.parties.length === 0 ? <p className="empty">台帳にやり取りがまだありません。</p> : null}
      {r.ok ? (
        <div className="watch-grid">
          {r.parties.map((p) => (
            <Link key={p.name} href={`/partners/${encodeURIComponent(p.name)}`} className="card watch-card">
              <header>
                <strong title={p.folder}>{p.name}</strong>
                <span className="meta">
                  最終 {jstStamp(p.latestAt).slice(5, 10)}・30日で{p.last30}件
                </span>
              </header>
              {p.latest.map((it) => (
                <p key={it.id} className="sum">
                  <span className="meta">
                    {jstStamp(it.occurred_at).slice(5, 10)} {CHANNEL_LABEL[it.channel] || it.channel}{" "}
                    {it.direction === "outbound" ? "自分→" : "←相手"}
                  </span>{" "}
                  {clip(cleanBody(it.summary || it.subject || "").replace(/\s+/g, " "), 70)}
                </p>
              ))}
            </Link>
          ))}
        </div>
      ) : null}
    </Shell>
  );
}
