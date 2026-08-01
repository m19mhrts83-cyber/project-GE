import BulkSkipNonPartnerButton from "@/components/BulkSkipNonPartnerButton";
import Shell from "@/components/Shell";
import {
  LEVEL_LABEL,
  HomeLevel,
  laneLabel,
  mailPriorityToLevel,
  watchSortKey,
} from "@/lib/homeLevels";
import {
  parseOtherMailDigest,
  type OtherMailDigest,
} from "@/lib/otherMailDigest";
import { createClient } from "@/lib/supabase/server";

function fallbackDigest(
  otherMails: {
    subject: string | null;
    from_email: string | null;
    partner: string | null;
    summary: string | null;
    priority: string | null;
  }[],
): OtherMailDigest {
  const n = otherMails.length;
  if (n === 0) {
    return {
      overview: "パートナー以外の未読はありません。",
      action_items: [],
      lines: [],
      pending_count: 0,
    };
  }
  const domains = new Map<string, number>();
  for (const m of otherMails) {
    const from = m.from_email || m.partner || "不明";
    const dom = from.includes("@") ? from.split("@").pop() || from : from;
    domains.set(dom, (domains.get(dom) || 0) + 1);
  }
  const top = [...domains.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([d, c]) => `${d}×${c}`)
    .join("、");
  const action = otherMails
    .filter((m) => mailPriorityToLevel(m.priority) === "attention")
    .slice(0, 5)
    .map((m) => ({
      subject: m.subject || "（件名なし）",
      from: m.from_email || m.partner || undefined,
      reason: "優先度: 要確認（参考）",
    }));
  return {
    overview: `未読 ${n} 件。主な差出: ${top || "—"}。ざざっと見て、残したいものだけ開いてください。`,
    action_items: action,
    lines: otherMails.slice(0, 4).map((m) => {
      const who = m.from_email || m.partner || "—";
      return `${who}: ${m.subject || "（件名なし）"}`;
    }),
    pending_count: n,
  };
}

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
    const m = v.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
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

  const digest =
    parseOtherMailDigest(metaMap.other_mail_digest) ||
    fallbackDigest(otherMails);
  const actionItems = digest.action_items || [];

  return (
    <Shell active="/">
      <h1>ホーム</h1>
      <p className="sub">
        パートナー → 状況ウォッチ → その他メールの順。カードや行をタップすると詳細へ。
      </p>

      <p className="home-sync" aria-label="最終同期">
        <span>
          最終同期 cloud <strong>{fmtSync(cloudAt)}</strong>
        </span>
        <span className="home-sync-sep">·</span>
        <span>
          mac_morning <strong>{fmtSync(macMorningAt)}</strong>
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

      {/* 1. パートナー */}
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

      {/* 2. 状況ウォッチ */}
      <div className="home-band home-band-watch">
        <div className="home-band-head">
          <h2 className="home-band-title">状況ウォッチ</h2>
          <p className="home-band-sub">仕組み・還元・同期などの健康診断</p>
        </div>

        <div className="stats home-stats">
          <div className="stat level-attention">
            要確認 <strong>{counts.attention}</strong>
          </div>
          <div className="stat level-warn">
            注意 <strong>{counts.warn}</strong>
          </div>
          <div className="stat level-info">
            参考 <strong>{counts.info}</strong>
          </div>
        </div>

        <section className="home-section">
          <div className="home-section-head">
            <h3>要フォロー</h3>
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
      </div>

      {/* 3. その他メール */}
      <div className="home-band home-band-other">
        <div className="home-band-head">
          <h2 className="home-band-title">その他メール</h2>
          <p className="home-band-sub">
            未読 {otherMails.length}
            {digest.generated_at
              ? ` · 要約 ${fmtSync(digest.generated_at)}`
              : ""}
          </p>
        </div>

        <p className="other-mail-hint">
          ざざっと見て、残したい／対応したいものだけ開く。終わったら一括スキップ。
        </p>

        <div className="other-mail-digest">
          <p className="other-mail-overview">
            {digest.overview || "（要約未生成。一覧をご確認ください）"}
          </p>
          {(digest.lines || []).length > 0 ? (
            <ul className="other-mail-lines">
              {(digest.lines || []).slice(0, 5).map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ul>
          ) : null}
          {actionItems.length > 0 ? (
            <div className="other-mail-actions" role="status">
              <p className="other-mail-actions-title">対応した方がよさそう</p>
              <ul>
                {actionItems.slice(0, 5).map((a, i) => (
                  <li key={a.id || i}>
                    {a.id ? (
                      <a href={`/mail/${encodeURIComponent(a.id)}`}>
                        {a.subject || "（件名なし）"}
                      </a>
                    ) : (
                      <span>{a.subject || "（件名なし）"}</span>
                    )}
                    {a.from ? (
                      <span className="meta"> · {a.from}</span>
                    ) : null}
                    {a.reason ? (
                      <span className="other-mail-reason"> — {a.reason}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : otherMails.length > 0 ? (
            <p className="other-mail-no-action">特に緊急候補なし</p>
          ) : null}
        </div>

        <div className="other-mail-toolbar">
          <BulkSkipNonPartnerButton
            path="/"
            pendingCount={otherMails.length}
            actionCandidateCount={actionItems.length}
          />
          <a href="/general" className="home-more">
            レーンへ →
          </a>
        </div>

        <section className="home-section">
          <div className="home-section-head">
            <h3>一覧</h3>
            <span className="meta">クリックで詳細</span>
          </div>
          {otherMails.length === 0 ? (
            <p className="empty">パートナー以外の未読はありません</p>
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
            レーン別: <a href="/general">それ以外</a>
            {" · "}
            <a href="/openchat">オプチャ</a>
          </p>
        </section>
      </div>

      <details className="home-meta">
        <summary>同期情報（詳細）</summary>
        <div className="stats" style={{ marginTop: 10 }}>
          <div className="stat">cloud {fmtSync(cloudAt)}</div>
          <div className="stat">mac_morning {fmtSync(macMorningAt)}</div>
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
