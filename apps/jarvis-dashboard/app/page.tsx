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
  fmtYen,
  parseOccupancySummary,
  previousYmJst,
  summarizeUnits,
  type PropertyUnit,
} from "@/lib/occupancy";
import { parseOpenchatDigest } from "@/lib/openchatDigest";
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

  const targetYm = previousYmJst();
  const { data: metricRows } = await supabase
    .from("metrics")
    .select("metric,entity,value,recorded_at")
    .in("metric", ["cashflow", "rent_income"])
    .order("recorded_at", { ascending: false })
    .limit(200);

  const metricLatest = new Map<string, number>();
  const metricMonths = new Set<string>();
  for (const r of metricRows || []) {
    const ym = String(r.recorded_at).slice(0, 7);
    metricMonths.add(ym);
    const key = `${ym}|${r.entity}|${r.metric}`;
    if (!metricLatest.has(key)) metricLatest.set(key, Number(r.value));
  }
  const financeYm = metricMonths.has(targetYm)
    ? targetYm
    : [...metricMonths].sort().reverse().find(
        (ym) =>
          metricLatest.has(`${ym}|corporate|cashflow`) ||
          metricLatest.has(`${ym}|personal|cashflow`),
      ) || targetYm;
  const pickMetric = (ent: string, metric: string) =>
    metricLatest.get(`${financeYm}|${ent}|${metric}`);

  const { data: unitRows } = await supabase
    .from("property_units")
    .select(
      "id,property_id,property_name,room,status,rent,note,source,payload,updated_at",
    )
    .order("property_id")
    .order("room");
  const units = (unitRows || []) as PropertyUnit[];
  const fromUnits = summarizeUnits(units);
  const occupancy =
    fromUnits.total > 0
      ? fromUnits
      : parseOccupancySummary(metaMap.occupancy_summary) || fromUnits;

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
        パートナー → モチベーション／満室 → 状況ウォッチ → その他メール → 神大家オプチャまとめの順。
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

      {/* 2. モチベーション数値＋全体満室率1行 */}
      <div className="home-band home-band-metrics">
        <div className="home-band-head">
          <h2 className="home-band-title">モチベーション数値</h2>
          <p className="home-band-sub">
            表示月 {financeYm}
            {financeYm !== targetYm ? `（先月 ${targetYm} は未取込）` : ""}
          </p>
        </div>
        <div className="stats home-stats">
          <div className="stat">
            法人 手残り{" "}
            <strong>{fmtYen(pickMetric("corporate", "cashflow"))}</strong>
          </div>
          <div className="stat">
            個人 手残り{" "}
            <strong>{fmtYen(pickMetric("personal", "cashflow"))}</strong>
          </div>
          <div className="stat">
            法人 家賃{" "}
            <strong>{fmtYen(pickMetric("corporate", "rent_income"))}</strong>
          </div>
          <div className="stat">
            個人 家賃{" "}
            <strong>{fmtYen(pickMetric("personal", "rent_income"))}</strong>
          </div>
        </div>
        <p className="home-occupancy-one-liner">
          全体満室率{" "}
          <strong>
            {occupancy.total ? `${occupancy.rate_pct}%` : "—"}
          </strong>
          {occupancy.total
            ? `（${occupancy.occupied}/${occupancy.total}戸）`
            : ""}
          {" · "}
          <a href="/properties" className="home-more">
            所有物件へ →
          </a>
        </p>
        <p className="home-metrics-more">
          <a href="/metrics" className="home-more">
            数値の詳細 →
          </a>
        </p>
      </div>

      {/* 3. 状況ウォッチ */}
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

      {/* 5. 神大家オプチャまとめ */}
      <div className="home-band home-band-openchat">
        <div className="home-band-head">
          <h2 className="home-band-title">神大家オプチャまとめ</h2>
          <p className="home-band-sub">大家業に役立ちそうな直近情報（返信提案なし）</p>
        </div>
        {(() => {
          const oc = parseOpenchatDigest(metaMap.openchat_digest);
          const groups = oc?.groups || [];
          return (
            <>
              {oc?.overview ? (
                <p className="openchat-digest-overview">{oc.overview}</p>
              ) : null}
              {groups.length === 0 ? (
                <p className="empty">
                  直近の有益情報はありません。{" "}
                  <a href="/openchat" className="home-more">
                    オプチャ一覧 →
                  </a>
                </p>
              ) : (
                <div className="watch-grid">
                  {groups.map((g) => (
                    <a
                      key={g.slug || g.name}
                      href={`/openchat/${g.slug || encodeURIComponent(g.name.replace(/\s+/g, "_"))}`}
                      className="card watch-card home-openchat-card"
                    >
                      <header>
                        <span className="lvl">有益</span>
                        <strong>{g.name}</strong>
                        {g.updated_at ? (
                          <span className="meta">{g.updated_at}</span>
                        ) : null}
                      </header>
                      <ul className="openchat-group-lines">
                        {(g.lines || []).slice(0, 3).map((ln, i) => (
                          <li key={i}>{ln}</li>
                        ))}
                      </ul>
                    </a>
                  ))}
                </div>
              )}
              {groups.length > 0 ? (
                <p className="home-metrics-more">
                  <a href="/openchat" className="home-more">
                    オプチャ一覧 →
                  </a>
                </p>
              ) : null}
            </>
          );
        })()}
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
