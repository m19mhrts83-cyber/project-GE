import { LEVEL_LABEL, mailPriorityToLevel } from "@/lib/homeLevels";
import { isMailActionExcluded } from "@/lib/selfEmails";
import { createClient } from "@/lib/supabase/server";
import { CHANNEL_LABEL, clip, cleanBody, jstStamp } from "@/lib/commHistory";
import { loadPartySummaries } from "@/lib/commHistoryServer";

export default async function HomePartnerBand() {
  const supabase = await createClient();
  const { data: mailRows } = await supabase
    .from("triage_items")
    .select(
      "id,lane,kind,status,partner,folder,subject,received_at,summary,priority,from_email,original_body",
    )
    .eq("status", "pending")
    .eq("lane", "partner")
    .neq("kind", "activity")
    .order("received_at", { ascending: false })
    .limit(40);
  const recent = await loadPartySummaries({ scan: 400, perParty: 1 }).catch(() => null);
  const recentParties = recent && recent.ok ? recent.parties.slice(0, 6) : [];

  const partnerMails = (mailRows || [])
    .filter(
      (m) =>
        !isMailActionExcluded({
          fromEmail: m.from_email,
          body: m.original_body,
        }),
    )
    .slice()
    .sort((a, b) => {
      const order = { attention: 0, warn: 1, info: 2 } as const;
      return (
        order[mailPriorityToLevel(a.priority)] -
        order[mailPriorityToLevel(b.priority)]
      );
    });

  return (
    <div className="home-band home-band-mail">
      <div className="home-band-head">
        <h2 className="home-band-title">パートナー</h2>
        <p className="home-band-sub">未読 {partnerMails.length}</p>
      </div>
      <section className="home-section">
        <div className="home-section-head">
          <h3>未読</h3>
          <a href="/partner" className="home-more">
            レーンへ →
          </a>
        </div>
        {partnerMails.length === 0 ? (
          <p className="empty">パートナーの未読はありません</p>
        ) : (
          <div className="watch-grid">
            {partnerMails.map((it) => {
              const level = mailPriorityToLevel(it.priority);
              const who = it.partner || it.from_email || "—";
              const oneLine = (it.summary || "").replace(/\s+/g, " ").trim();
              return (
                <a
                  key={it.id}
                  href={`/mail/${encodeURIComponent(it.id)}`}
                  className={`card watch-card home-partner-card level-${level}`}
                >
                  <header>
                    <span className="lvl">{LEVEL_LABEL[level]}</span>
                    <strong title={who}>{who}</strong>
                    {it.received_at ? (
                      <span className="meta">{it.received_at}</span>
                    ) : null}
                  </header>
                  <p className="mail-subject home-partner-subject">
                    {it.subject || "（件名なし）"}
                  </p>
                  {oneLine ? <p className="sum">{oneLine}</p> : null}
                  {it.folder ? <p className="meta">{it.folder}</p> : null}
                </a>
              );
            })}
          </div>
        )}
      </section>
      {recentParties.length ? (
        <section className="home-section">
          <div className="home-section-head">
            <h3>最近のやり取り</h3>
            <a href="/partners" className="home-more">
              相手ごとに見る →
            </a>
          </div>
          <div className="watch-grid">
            {recentParties.map((p) => {
              const it = p.latest[0];
              return (
                <a key={p.name} href={`/partners/${encodeURIComponent(p.name)}`} className="card watch-card home-partner-card">
                  <header>
                    <strong title={p.folder}>{p.name}</strong>
                    <span className="meta">
                      {jstStamp(p.latestAt).slice(5, 16)} {it ? CHANNEL_LABEL[it.channel] || it.channel : ""}
                    </span>
                  </header>
                  {it ? (
                    <p className="sum">
                      {it.direction === "outbound" ? "自分→ " : "←相手 "}
                      {clip(cleanBody(it.summary || it.subject || "").replace(/\s+/g, " "), 60)}
                    </p>
                  ) : null}
                </a>
              );
            })}
          </div>
        </section>
      ) : null}
    </div>
  );
}
