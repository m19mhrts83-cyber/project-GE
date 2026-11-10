import Link from "next/link";
import Shell from "@/components/Shell";
import CopyForAi from "@/components/CopyForAi";
import DecisionRetro from "@/components/DecisionRetro";
import { createClient } from "@/lib/supabase/server";
import { fmtYen, formatJstDateTime } from "@/lib/format";
import { RETRO_QUALITY } from "@/lib/kurashiftDecision";
import { loadDecisionRows } from "@/lib/kurashiftDecisionLoad";
import {
  canRetro,
  retroCandidates,
  summarize,
  summarizeRetro,
  toAiBrief,
  type DecisionRow,
} from "@/lib/kurashiftDecisionLog";

export const dynamic = "force-dynamic";

const DAYS = 90;
const LOOPWARE_REVIEW_URL =
  (process.env.NEXT_PUBLIC_LOOPWARE_URL || "https://jarvis-loopware.vercel.app").replace(/\/$/, "") +
  "/review";

const OUTCOME_LABEL: Record<DecisionRow["outcome"], string> = {
  take: "進めた",
  ng: "見送った",
  hesitate: "迷った",
  later: "後で",
  note: "メモ",
};

const KIND_TABS = [
  { key: "all", label: "すべて" },
  { key: "money", label: "資金移動" },
  { key: "deal", label: "物件" },
] as const;

function pct(n: number | null): string {
  return n === null ? "—" : `${Math.round(n * 100)}%`;
}

function dayKey(iso: string): string {
  return formatJstDateTime(iso).slice(0, 10);
}

function dayLabel(key: string): string {
  const d = new Date(`${key}T00:00:00+09:00`);
  if (Number.isNaN(d.getTime())) return key;
  return new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo",
    month: "long",
    day: "numeric",
    weekday: "short",
  }).format(d);
}

function hrefOf(r: DecisionRow): string {
  return r.kind === "money"
    ? "/money-ops"
    : `/realestate/deals?deal=${encodeURIComponent(r.targetId)}`;
}

export default async function DecisionsPage({
  searchParams,
}: {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = (await searchParams) || {};
  const kindParam = typeof sp.kind === "string" ? sp.kind : "all";
  const kind = kindParam === "money" || kindParam === "deal" ? kindParam : "all";

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const [rows, { data: voices }] = await Promise.all([
    loadDecisionRows(supabase, DAYS),
    supabase
      .from("kurashift_consultations")
      .select("id, title, body, status, created_at, metadata")
      .contains("metadata", { kind: "app_feedback" })
      .order("created_at", { ascending: false })
      .limit(5),
  ]);

  const all = summarize(rows);
  const retro = summarizeRetro(rows);
  const waiting = retroCandidates(rows, new Date());
  const shown = kind === "all" ? rows : rows.filter((r) => r.kind === kind);

  const groups: { key: string; items: DecisionRow[] }[] = [];
  for (const r of shown.slice(0, 200)) {
    const k = dayKey(r.at);
    const g = groups[groups.length - 1];
    if (g && g.key === k) g.items.push(r);
    else groups.push({ key: k, items: [r] });
  }

  return (
    <Shell active="/decisions" email={user?.email ?? null}>
      <div className="dl-head">
        <div>
          <p className="page-kicker">ループウェア</p>
          <h1>お金の判断ログ</h1>
          <p className="sub">
            決める → 理由をひとつ残す → 後日に答え合わせ → 週1で基準を見直す。直近{DAYS}日ぶんです。
          </p>
        </div>
        <div className="dl-head-actions">
          <CopyForAi text={toAiBrief(rows)} count={rows.length} />
          <a className="btn" href={LOOPWARE_REVIEW_URL} target="_blank" rel="noreferrer">
            Nody の週1レビュー ↗
          </a>
        </div>
      </div>

      <div className="dl-stats">
        <div className="dl-stat">
          <span className="dl-stat-label">判断</span>
          <span className="dl-stat-num">
            {all.total}
            <small>件</small>
          </span>
          <span className="dl-stat-sub">
            進めた {all.take}・見送った {all.ng}・迷った {all.hesitate}
          </span>
          {all.total > 0 ? (
            <span className="dl-bar" aria-hidden>
              <i className="o-take" style={{ flexGrow: all.take }} />
              <i className="o-ng" style={{ flexGrow: all.ng }} />
              <i className="o-hesitate" style={{ flexGrow: all.hesitate }} />
              <i className="o-later" style={{ flexGrow: all.later }} />
            </span>
          ) : null}
        </div>
        <div className="dl-stat">
          <span className="dl-stat-label">理由が残っている</span>
          <span className="dl-stat-num">{pct(all.reasonRate)}</span>
          <span className="dl-stat-sub">理由は任意。残すほど「前回と同じ」が効きます</span>
        </div>
        <div className="dl-stat">
          <span className="dl-stat-label">答え合わせ</span>
          <span className="dl-stat-num">
            {retro.total}
            <small>件</small>
          </span>
          <span className="dl-stat-sub">
            {retro.total
              ? `良かった ${retro.good}・まあまあ ${retro.meh}・やり直したい ${retro.regret}`
              : `待ち ${waiting.length} 件（進めてから14日後に出ます）`}
          </span>
        </div>
        <div className="dl-stat">
          <span className="dl-stat-label">基準の候補</span>
          <span className="dl-stat-num">
            {all.ruleCandidates.length}
            <small>件</small>
          </span>
          <span className="dl-stat-sub">「次も同じに」を付けた判断。採用は週1で決める</span>
        </div>
      </div>

      {waiting.length > 0 ? (
        <section className="card dl-waiting">
          <header>
            <span className="lvl">答え合わせ</span>
            <strong>進めた判断は、実際どうでしたか</strong>
          </header>
          <ul className="dl-wait-list">
            {waiting.slice(0, 5).map((r) => (
              <li key={r.key}>
                <div className="dl-wait-main">
                  <span className="meta">{formatJstDateTime(r.at).slice(0, 10)}</span>
                  <a href={hrefOf(r)}>
                    <strong>{r.title}</strong>
                  </a>
                  <span className="meta">
                    {r.label}
                    {r.amountJpy !== null ? `・${fmtYen(r.amountJpy)}` : ""}
                    {r.reasonLabels.length ? `・${r.reasonLabels.join("／")}` : ""}
                  </span>
                </div>
                <DecisionRetro kind={r.kind} targetId={r.targetId} refId={r.refId} />
              </li>
            ))}
          </ul>
          {waiting.length > 5 ? (
            <p className="meta">ほか {waiting.length - 5} 件</p>
          ) : null}
        </section>
      ) : null}

      <div className="dl-two">
        <section className="card">
          <header>
            <span className="lvl">共通パターン</span>
            <strong>同じ理由が2件以上</strong>
          </header>
          {all.patterns.length === 0 ? (
            <p className="meta" style={{ marginTop: 6 }}>
              まだありません。1件だけの理由は一般化しません。
            </p>
          ) : (
            <ul className="dl-patterns">
              {all.patterns.map((p) => (
                <li key={`${p.kind}:${p.outcome}:${p.tag}`}>
                  <span className={`dl-dot o-${p.outcome}`} aria-hidden />
                  <span>
                    {p.kind === "money" ? "資金移動" : "物件"}を{OUTCOME_LABEL[p.outcome]}理由
                  </span>
                  <strong>{p.label}</strong>
                  <span className="dl-count">{p.count}件</span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="card">
          <header>
            <span className="lvl">基準の候補</span>
            <strong>「次も同じに」を付けた判断</strong>
          </header>
          {all.ruleCandidates.length === 0 ? (
            <p className="meta" style={{ marginTop: 6 }}>
              同じ理由を2回選ぶと、判断メモが「次も同じに？」と聞きます。
            </p>
          ) : (
            <ul className="dl-patterns">
              {all.ruleCandidates.slice(0, 8).map((r) => (
                <li key={r.key}>
                  <span className={`dl-dot o-${r.outcome}`} aria-hidden />
                  <span>{r.label}</span>
                  <strong>{r.reasonLabels.join("・") || r.note || "（理由なし）"}</strong>
                  <span className="dl-count">{r.title}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="card dl-timeline-card">
        <header className="dl-timeline-head">
          <div className="dl-timeline-title">
            <span className="lvl">一覧</span>
            <strong>新しい順</strong>
          </div>
          <nav className="dl-tabs" aria-label="種類で絞る">
            {KIND_TABS.map((t) => (
              <Link
                key={t.key}
                href={t.key === "all" ? "/decisions" : `/decisions?kind=${t.key}`}
                className={kind === t.key ? "on" : ""}
              >
                {t.label}
              </Link>
            ))}
          </nav>
        </header>

        {groups.length === 0 ? (
          <div className="dl-empty">
            <strong>まだ記録がありません</strong>
            <p>
              <a href="/money-ops">資金移動</a>の「承認」や、
              <a href="/realestate/deals">物件</a>の「見送り」を押すと判断メモが出て、ここに並びます。
            </p>
          </div>
        ) : (
          groups.map((g) => (
            <div className="dl-day" key={g.key}>
              <div className="dl-day-label">{dayLabel(g.key)}</div>
              <ul className="dl-items">
                {g.items.map((r) => (
                  <li key={r.key} className="dl-item">
                    <span className={`dl-dot o-${r.outcome}`} aria-hidden />
                    <div className="dl-item-body">
                      <div className="dl-item-top">
                        <span className={`dl-verdict o-${r.outcome}`}>{r.label}</span>
                        <a href={hrefOf(r)} className="dl-item-title">
                          {r.title}
                        </a>
                        {r.amountJpy !== null ? (
                          <span className="dl-amount">{fmtYen(r.amountJpy)}</span>
                        ) : null}
                        <span className="dl-time">
                          {r.kind === "money" ? "資金移動" : "物件"}・
                          {formatJstDateTime(r.at).slice(11)}
                        </span>
                      </div>
                      {r.reasonLabels.length || r.always || r.note ? (
                        <div className="dl-item-reason">
                          {r.reasonLabels.map((l) => (
                            <span className="decision-tag" key={l}>
                              {l}
                            </span>
                          ))}
                          {r.always ? (
                            <span className="decision-tag always">次も同じに</span>
                          ) : null}
                          {r.note ? <span className="dl-note">{r.note}</span> : null}
                        </div>
                      ) : (
                        <div className="decision-empty-reason">理由なし</div>
                      )}
                      {r.retro ? (
                        <div className="dl-item-retro">
                          <span className={`retro-badge q-${r.retro.quality}`}>
                            答え合わせ：{RETRO_QUALITY[r.retro.quality]}
                          </span>
                          {r.retro.note ? <span className="dl-note">{r.retro.note}</span> : null}
                        </div>
                      ) : canRetro(r) ? (
                        <div className="dl-item-retro">
                          <DecisionRetro
                            kind={r.kind}
                            targetId={r.targetId}
                            refId={r.refId}
                            compact
                          />
                        </div>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
      </section>

      <section className="card">
        <header>
          <span className="lvl">使い勝手への声</span>
          <strong>画面の右下「声を残す」から</strong>
        </header>
        {(voices ?? []).length === 0 ? (
          <p className="meta" style={{ marginTop: 6 }}>
            使っていて「見づらい」「手間が多い」と感じたら、その画面のまま残してください。週次の見直しで拾って直します。
          </p>
        ) : (
          <ul className="dl-voices">
            {(voices ?? []).map((v) => {
              const md = (v.metadata || {}) as { path?: string; tag_labels?: string[] };
              return (
                <li key={v.id}>
                  <span className="meta">{formatJstDateTime(v.created_at).slice(5, 10)}</span>
                  <a href={`/consultations/${v.id}`}>
                    <code>{md.path || "/"}</code>
                  </a>
                  <span>
                    {(md.tag_labels || []).join("・")}
                    {v.body ? `　${v.body}` : ""}
                  </span>
                  <span className={`dl-voice-status s-${v.status}`}>
                    {v.status === "open" ? "未対応" : v.status === "decided" ? "対応済み" : "保管"}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </Shell>
  );
}
