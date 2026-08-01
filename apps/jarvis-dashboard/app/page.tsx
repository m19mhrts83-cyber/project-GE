import Link from "next/link";
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

  const mailCounts = { attention: 0, warn: 0, info: 0 };
  for (const m of mails) {
    mailCounts[mailPriorityToLevel(m.priority)] += 1;
  }

  return (
    <Shell active="/">
      <h1>ホーム</h1>
      <p className="sub">
        PC起動時にパッと見る画面。上で「見なきゃあかん」項目、下でメールをざっと確認。
        気になる行をタップすると詳細へ。
      </p>

      <div className="stats">
        <div className="stat level-attention">
          要確認 <strong>{counts.attention + mailCounts.attention}</strong>
        </div>
        <div className="stat level-warn">
          注意 <strong>{counts.warn + mailCounts.warn}</strong>
        </div>
        <div className="stat level-info">
          参考 <strong>{counts.info + mailCounts.info}</strong>
        </div>
        <div className="stat">
          メール pending <strong>{mails.length}</strong>
        </div>
      </div>

      <section className="home-section">
        <div className="home-section-head">
          <h2>要確認（状況ウォッチ）</h2>
          <Link href="/situation" className="home-more">
            すべて →
          </Link>
        </div>
        {watchNeed.length === 0 ? (
          <p className="empty" style={{ padding: "12px 0" }}>
            いま要注意の項目はありません（ok のみ、または未 push）
          </p>
        ) : (
          <div className="watch-grid">
            {watchNeed.map((it) => {
              const level = (["attention", "warn", "info"].includes(it.level)
                ? it.level
                : "info") as HomeLevel;
              return (
                <Link
                  key={it.id}
                  href="/situation"
                  className={`card watch-card level-${level}`}
                >
                  <header>
                    <span className="lvl">{LEVEL_LABEL[level]}</span>
                    <strong>{it.title}</strong>
                  </header>
                  <p className="sum">{it.summary}</p>
                  {it.source ? (
                    <p className="meta">{it.source}</p>
                  ) : null}
                </Link>
              );
            })}
          </div>
        )}
      </section>

      <section className="home-section">
        <div className="home-section-head">
          <h2>メール（ざっと見る）</h2>
          <span className="meta">クリックで詳細</span>
        </div>
        {mails.length === 0 ? (
          <p className="empty" style={{ padding: "12px 0" }}>
            pending のメールはありません
          </p>
        ) : (
          <ul className="mail-skim">
            {mails.map((it) => {
              const level = mailPriorityToLevel(it.priority);
              const who = it.partner || it.from_email || "—";
              const oneLine = (it.summary || "").replace(/\s+/g, " ").trim();
              return (
                <li key={it.id}>
                  <Link
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
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
        <p className="home-lane-links">
          レーン別:{" "}
          <Link href="/partner">パートナー</Link>
          {" · "}
          <Link href="/openchat">オプチャ</Link>
          {" · "}
          <Link href="/general">それ以外</Link>
        </p>
      </section>

      <details className="home-meta">
        <summary>同期情報</summary>
        <div className="stats" style={{ marginTop: 10 }}>
          <div className="stat">
            triage {metaMap.triage_pushed_at ?? "未push"}
          </div>
          <div className="stat">
            watch {metaMap.watch_pushed_at ?? "未push"}
          </div>
          <div className="stat">
            経路 {metaMap.triage_source ?? "—"}
          </div>
          <div className="stat">
            Mac {metaMap.mac_triage_pushed_at ?? "—"}
          </div>
          <div className="stat">
            GHA {metaMap.gha_triage_pushed_at ?? "—"}
          </div>
        </div>
      </details>
    </Shell>
  );
}
