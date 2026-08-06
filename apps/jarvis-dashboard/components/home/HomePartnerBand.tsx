import { LEVEL_LABEL, mailPriorityToLevel } from "@/lib/homeLevels";
import { createClient } from "@/lib/supabase/server";

export default async function HomePartnerBand() {
  const supabase = await createClient();
  const { data: mailRows } = await supabase
    .from("triage_items")
    .select(
      "id,lane,kind,status,partner,folder,subject,received_at,summary,priority,from_email",
    )
    .eq("status", "pending")
    .eq("lane", "partner")
    .neq("kind", "activity")
    .order("received_at", { ascending: false })
    .limit(40);

  const partnerMails = (mailRows || []).slice().sort((a, b) => {
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
    </div>
  );
}
