import Link from "next/link";
import Shell from "@/components/Shell";
import { CHANNEL_LABEL, cleanBody, clip, itemText, jstStamp } from "@/lib/commHistory";
import { loadPartyTimeline } from "@/lib/commHistoryServer";

export const dynamic = "force-dynamic";
export const metadata = { title: "パートナーのやり取り｜Jarvis" };

export default async function PartnerTimelinePage({ params }: { params: Promise<{ name: string }> }) {
  const { name: raw } = await params;
  const name = decodeURIComponent(raw || "");
  const r = await loadPartyTimeline(name, 40);
  return (
    <Shell active="/partners">
      <p className="sub">
        <Link href="/partners">← パートナーのやり取り</Link>
      </p>
      <h1>{name}</h1>
      {!r.ok ? <p className="empty">読み込みに失敗: {r.error}</p> : null}
      {r.ok && !r.party ? <p className="empty">台帳の名簿にこの相手がいません。</p> : null}
      {r.ok && r.party ? (
        <>
          <p className="sub">
            直近 {r.items.length} 件（新しい順・チャネル横断）。全文の正本は OneDrive の {r.party.partner_folder || "やり取り"}/5.やり取り.md です。
          </p>
          {r.items.length === 0 ? <p className="empty">やり取りはまだありません。</p> : null}
          {r.items.map((it, i) => {
            const body = itemText(it);
            const head = clip(cleanBody(it.summary || it.subject || body).replace(/\s+/g, " "), 90);
            return (
              <details key={it.id} className="card" open={i < 3} style={{ marginBottom: 8 }}>
                <summary>
                  <span className="meta">
                    {jstStamp(it.occurred_at)}｜{CHANNEL_LABEL[it.channel] || it.channel}｜
                    {it.direction === "outbound" ? "自分から送信" : "相手から"}
                  </span>{" "}
                  {it.channel === "gmail" && it.subject ? <strong>{cleanBody(it.subject)} </strong> : null}
                  {i < 3 ? null : head}
                </summary>
                <pre style={{ whiteSpace: "pre-wrap", margin: "8px 0 0", fontFamily: "inherit" }}>{body}</pre>
              </details>
            );
          })}
        </>
      ) : null}
    </Shell>
  );
}
