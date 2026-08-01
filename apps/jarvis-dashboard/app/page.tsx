import Shell from "@/components/Shell";
import {
  LEVEL_LABEL,
  HomeLevel,
  laneLabel,
  mailPriorityToLevel,
  watchSortKey,
} from "@/lib/homeLevels";
import { createClient } from "@/lib/supabase/server";

export default async function HomePage() {
  const supabase = await createClient();

  const { data: watchRows } = await supabase
    .from("watch_status")
    .select("*")
    .eq("status", "active");

  const { data: mailRows } = await supabase
    .from("triage_items")
    .select(
      "id,lane,kind,status,partner,folder,subject,received_at,summary,priority,from_email"
    )
    .eq("status", "pending")
    .neq("kind", "activity")
    .order("received_at", { ascending: false })
    .limit(40);

  const { data: meta } = await supabase.from("sync_meta").select("key,value");
  const metaMap = Object.fromEntries((meta || []).map((m) => [m.key, m.value]));

  const fmtSync = (v: string | undefined) => {
    if (!v) return "—";
    // 2026-08-01T09:12:00+0900 → 08/01 09:12
    const m = v.match(
      /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/
    );
    if (m) return `${m[2]}/${m[3]} ${m[4]}:${m[5]}`;
    return v.length > 16 ? v.slice(0, 16) : v;
  };
  const cloudAt =
    metaMap.gha_triage_pushed_at ||
    metaMap.gha_watch_pushed_at ||
    metaMap.gha_heartbeat_at;
  const macMorningAt = metaMap.mac_morning_refreshed_at;
  const macMorningOk = metaMap.mac_morning_refresh_ok;

  const watchNeed = (watchRows || [])
    .filter((w) => w.level !== "ok")
    .sort(
      (a, b) =>
        watchSortKey(a.level) - watchSortKey(b.level) ||
        String(b.updated_at || "").localeCompare(String(a.updated_at || ""))
    );

  const counts = { attention: 0, warn: 0, info: 0 };
  for (const w of watchNeed) {
    const lv = (w.level || "info") as HomeLevel;
    if (lv in counts) counts[lv] += 1;
  }

  const mails = (mailRows || []).slice().sort((a, b) => {
    const la = mailPriorityToLevel(a.priority);
    const lb = mailPriorityToLevel(b.priority);
    const order = { attention: 0, warn: 1, info: 2 } as const;
    return order[la] - order[lb];
  });

  const partnerMails = mails.filter((m) => m.lane === "partner");
  const otherMails = mails.filter((m) => m.lane !== "partner");

  const mailCounts = { attention: 0, warn: 0, info: 0 };
  for (const m of mails) {
    mailCounts[mailPriorityToLevel(m.priority)] += 1;
  }

  return (
    <Shell active="/">
      <h1>ホーム</h1>
      <p className="sub">
        PC起動時にパッと見る画面。まずパートナー未読、次に状況ウォッチ、下でその他メール。
        カードや行をタップすると詳細へ。
      </p>

      <p className="home-sync" aria-label="最終同期">
        <span>
          最終同期 cloud{" "}
          <strong>{fmtSync(cloudAt)}</strong>
        </span>
        <span className="home-sync-sep">·</span>
        <span>
          mac_morning{" "}
          <strong>{fmtSync(macMorningAt)}</strong>
          {macMorningAt && macMorningOk === "0" ? (
            <span className="home-sync-warn">（一部失敗）</span>
          ) : null}
        </span>
      </p>

      <div className="home-legend" aria-label="優先度の凡例">
        <span className="home-legend-item">
          <span className="home-legend-swatch attention" />
          要確認
        </span>
        <span className="home-legend-item">
          <span className="home-legend-swatch warn" />
          注意
        </span>
        <span className="home-legend-item">
          <span className="home-legend-swatch info" />
          参考
        </span>
      </div>

      <div className="stats home-stats">
        <div className="stat level-attention">
          パートナー未読 <strong>{partnerMails.length}</strong>
        </div>
        <div className="stat level-attention">
          要確認 <strong>{counts.attention + mailCounts.attention}</strong>
        </div>
        <div className="stat level-warn">
          注意 <strong>{counts.warn + mailCounts.warn}</strong>
        </div>
        <div className="stat">
          メール pending <strong>{mails.length}</strong>
        </div>
      </div>

      <section className="home-section">
        <div className="home-section-head">
          <h2>パートナー（未読）</h2>
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

      <section className="home-section">
        <div className="home-section-head">
          <h2>要確認（状況ウォッチ）</h2>
          <a href="/situation" className="home-more">
            すべて →
          </a>
        </div>
        {watchNeed.length === 0 ? (
          <p className="empty">
            いま要注意の項目はありません（ok のみ、または未 push）
          </p>
        ) : (
          <div className="watch-grid">
            {watchNeed.map((it) => {
              const level = (
                ["attention", "warn", "info"].includes(it.level)
                  ? it.level
                  : "info"
              ) as HomeLevel;
              return (
                <a
                  key={it.id}
                  href="/situation"
                  className={`card watch-card level-${level}`}
                >
                  <header>
                    <span className="lvl">{LEVEL_LABEL[level]}</span>
                    <strong title={it.title}>{it.title}</strong>
                  </header>
                  <p className="sum">{it.summary}</p>
                  {it.source ? <p className="meta">{it.source}</p> : null}
                </a>
              );
            })}
          </div>
        )}
      </section>

      <section className="home-section">
        <div className="home-section-head">
          <h2>その他メール（ざっと見る）</h2>
          <span className="meta">クリックで詳細</span>
        </div>
        {otherMails.length === 0 ? (
          <p className="empty">パートナー以外の pending はありません</p>
        ) : (
          <ul className="mail-skim">
            {otherMails.map((it) => {
              const level = mailPriorityToLevel(it.priority);
              const who = it.partner || it.from_email || "—";
              const oneLine = (it.summary || "").replace(/\s+/g, " ").trim();
              return (
                <li key={it.id}>
                  <a
                    href={`/mail/${encodeURIComponent(it.id)}`}
                    className={`mail-row level-${level}`}
                  >
                    <span className="lvl">{LEVEL_LABEL[level]}</span>
                    <span className="mail-row-main">
                      <span className="mail-row-top">
                        <strong>{who}</strong>
                        <span className="meta">
                          {laneLabel(it.lane)}
                          {it.received_at ? ` · ${it.received_at}` : ""}
                        </span>
                      </span>
                      <span className="mail-subject">
                        {it.subject || "（件名なし）"}
                      </span>
                      {oneLine ? (
                        <span className="mail-preview">{oneLine}</span>
                      ) : null}
                    </span>
                    <span className="mail-chevron" aria-hidden>
                      ›
                    </span>
                  </a>
                </li>
              );
            })}
          </ul>
        )}
        <p className="home-lane-links">
          レーン別:{" "}
          <a href="/partner">パートナー</a>
          {" · "}
          <a href="/openchat">オプチャ</a>
          {" · "}
          <a href="/general">それ以外</a>
        </p>
      </section>

      <details className="home-meta">
        <summary>同期情報（詳細）</summary>
        <div className="stats" style={{ marginTop: 10 }}>
          <div className="stat">
            cloud {fmtSync(cloudAt)}
          </div>
          <div className="stat">
            mac_morning {fmtSync(macMorningAt)}
          </div>
          <div className="stat">
            triage {metaMap.triage_pushed_at ?? "未push"}
          </div>
          <div className="stat">
            watch {metaMap.watch_pushed_at ?? "未push"}
          </div>
          <div className="stat">経路 {metaMap.triage_source ?? "—"}</div>
          <div className="stat">
            Mac push {metaMap.mac_triage_pushed_at ?? "—"}
          </div>
          <div className="stat">
            GHA triage {metaMap.gha_triage_pushed_at ?? "—"}
          </div>
        </div>
      </details>
    </Shell>
  );
}
