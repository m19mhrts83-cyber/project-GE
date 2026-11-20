import Link from "next/link";
import Shell from "@/components/Shell";
import { CHANNEL_LABEL, cleanBody, clip, itemText, jstStamp } from "@/lib/commHistory";
import { loadPartyTimeline } from "@/lib/commHistoryServer";
import { loopwareHref } from "@/lib/loopwareLink";

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
          {r.pending.length ? (
            <section className="card" style={{ marginBottom: 16 }}>
              <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                <strong>返信待ち {r.pending.length}件</strong>
                <a className="btn primary" href={loopwareHref("/desk", { from: "partners" })} target="_blank" rel="noopener noreferrer">
                  判断デスクで直す・送る →
                </a>
              </header>
              {r.pending.map((p) => (
                <div key={p.id} style={{ marginTop: 10 }}>
                  <p className="meta">
                    {p.received_at ? jstStamp(p.received_at) : ""} {p.subject ? `「${clip(cleanBody(p.subject), 60)}」` : ""}
                  </p>
                  {p.draft_text?.trim() ? (
                    <details open>
                      <summary>今の下書き</summary>
                      <pre style={{ whiteSpace: "pre-wrap", margin: "6px 0 0", fontFamily: "inherit" }}>{p.draft_text}</pre>
                    </details>
                  ) : (
                    <p className="sum">下書きはまだありません。判断デスクで声で頼むと、下のやり取りを踏まえて作ります。</p>
                  )}
                </div>
              ))}
            </section>
          ) : null}
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
