import Link from "next/link";
import Shell from "@/components/Shell";
import VpointAckButton from "@/components/VpointAckButton";
import { createClient } from "@/lib/supabase/server";

const WATCH_ID = "vpoint";

type RateBucket = {
  rate_pct?: number | null;
  pt?: number | null;
  count?: number | null;
  samples?: { date?: string; desc?: string; pt?: number }[];
};

type GrantSummary = {
  target_month?: string | null;
  total_pt?: number | null;
  by_cadence?: {
    monthly?: number;
    daily?: number;
    other?: number;
  } | null;
  by_rate?: RateBucket[];
  insights?: string[];
  shop_up_ok?: boolean | null;
  condition_grants_ok?: boolean | null;
  source_note?: string | null;
  at?: string | null;
  grant_rule?: string | null;
};

type HistoryRow = {
  target_month?: string | null;
  total_pt?: number | null;
  by_cadence?: {
    monthly?: number;
    daily?: number;
    other?: number;
  } | null;
  insights?: string[];
  at?: string | null;
  source_note?: string | null;
};

type TeikiService = {
  id?: string;
  title?: string;
  status?: string;
  note?: string;
  payment_on_olive?: boolean;
  counts?: boolean | string;
};

type TeikiDraw = {
  at?: string | null;
  tickets_before?: number | null;
  tickets_after?: number | null;
  results_summary?: string | null;
  ok?: boolean;
};

type TeikiBarai = {
  enrolled?: string | null;
  service_count?: number | null;
  ticket_count?: number | null;
  w_chance_tickets?: number | null;
  last_check_at?: string | null;
  last_draw_at?: string | null;
  last_draw?: TeikiDraw | null;
  draw_history?: TeikiDraw[];
  services?: TeikiService[];
  interval_days?: number | null;
};

type PdcaItem = {
  id?: string;
  title?: string;
  detail?: string;
  how?: string;
  priority?: string;
};

type PdcaBoard = {
  at?: string | null;
  wins?: PdcaItem[];
  gaps?: PdcaItem[];
  next_actions?: PdcaItem[];
  freshness?: string[];
  user_intent_note?: string | null;
};

type BenefitTier = {
  id?: string;
  label?: string;
  threshold_yen?: number;
  reward?: string;
  threshold_status?: string;
  threshold_status_label?: string;
  source_note?: string | null;
  achieved_pct?: number | null;
  remaining_yen?: number | null;
  need_per_month_yen?: number | null;
  verdict?: string;
};

type BenefitCard = {
  id?: string;
  name?: string;
  short?: string;
  period_start?: string;
  period_end?: string;
  days_left?: number;
  months_left?: number;
  usage_yen?: number | null;
  usage_as_of?: string | null;
  usage_kind?: string | null;
  usage_source?: string | null;
  usage_caveat?: string | null;
  usage_stale_days?: number | null;
  pace_per_month_yen?: number | null;
  counts_note?: string | null;
  grant_note?: string | null;
  note?: string | null;
  tiers?: BenefitTier[];
};

type BenefitGrant = {
  label?: string;
  pt?: number;
  status?: string;
  granted_on?: string;
  period_start?: string;
  period_end?: string;
  source?: string;
};

type ExitItem = {
  label?: string;
  status?: string;
  status_label?: string;
  checked_on?: string;
  source?: string;
  featured?: boolean;
  note?: string | null;
  extra_notes?: string[];
};

type CardBenefit = {
  today?: string;
  cards?: BenefitCard[];
  recommendation?: { line?: string };
  scope_note?: string;
  olive_history?: {
    achieved?: BenefitGrant[];
    upcoming?: {
      label?: string;
      period_start?: string;
      period_end?: string;
      grant_timing?: string;
      mail_status?: { as_of?: string; text?: string; source?: string } | null;
    };
  };
  vpoint_exits?: { items?: ExitItem[]; official_sources?: string[] };
};

function fmtYen(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${Math.round(n).toLocaleString("ja-JP")}円`;
}

function verdictMark(v: string | undefined) {
  if (v === "届く" || v === "達成") return "○";
  if (v === "厳しい") return "△";
  return "×";
}

function fmtPt(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${Math.round(n).toLocaleString("ja-JP")}pt`;
}

function fmtRate(n: number | null | undefined) {
  if (n == null) return "不明";
  return `${n}%`;
}

function statusLabel(s: string | undefined) {
  switch (s) {
    case "done":
      return "済";
    case "excluded_keep_paypay":
      return "除外（PayPay維持）";
    case "confirm_needed":
      return "要確認";
    case "awaiting_first_charge":
      return "Olive課金待ち";
    case "candidate":
      return "候補";
    case "confirm":
      return "確認中";
    case "in_progress":
      return "進行中";
    default:
      return s || "—";
  }
}

export default async function VpointPage() {
  const supabase = await createClient();
  const { data: watch } = await supabase
    .from("watch_status")
    .select("*")
    .eq("id", WATCH_ID)
    .maybeSingle();

  const payload =
    watch?.payload && typeof watch.payload === "object"
      ? (watch.payload as Record<string, unknown>)
      : {};

  const summary = (
    payload.grant_summary && typeof payload.grant_summary === "object"
      ? (payload.grant_summary as GrantSummary)
      : {}
  ) as GrantSummary;

  const history = Array.isArray(payload.grant_history)
    ? (payload.grant_history as HistoryRow[])
    : [];

  const teiki =
    payload.teiki_barai && typeof payload.teiki_barai === "object"
      ? (payload.teiki_barai as TeikiBarai)
      : null;

  const ack =
    typeof payload.dashboard_ack_target_month === "string"
      ? payload.dashboard_ack_target_month
      : null;
  const target = summary.target_month || null;
  const hasGrant = target != null && summary.total_pt != null;
  const showBanner =
    typeof payload.show_banner === "boolean"
      ? payload.show_banner
      : Boolean(hasGrant && ack !== target);

  const bc = summary.by_cadence || {};
  const byRate = Array.isArray(summary.by_rate) ? summary.by_rate : [];
  const insights = Array.isArray(summary.insights) ? summary.insights : [];
  const cb =
    payload.card_benefit && typeof payload.card_benefit === "object"
      ? (payload.card_benefit as CardBenefit)
      : null;
  const cbCards = Array.isArray(cb?.cards) ? cb!.cards! : [];
  const cbGranted = Array.isArray(cb?.olive_history?.achieved) ? cb!.olive_history!.achieved! : [];
  const cbUpcoming = cb?.olive_history?.upcoming || null;
  const cbExits = Array.isArray(cb?.vpoint_exits?.items) ? cb!.vpoint_exits!.items! : [];
  const cbSources = Array.isArray(cb?.vpoint_exits?.official_sources)
    ? cb!.vpoint_exits!.official_sources!
    : [];
  const teikiServices = Array.isArray(teiki?.services) ? teiki!.services! : [];
  const pdca =
    payload.pdca_board && typeof payload.pdca_board === "object"
      ? (payload.pdca_board as PdcaBoard)
      : null;
  const pdcaWins = Array.isArray(pdca?.wins) ? pdca!.wins! : [];
  const pdcaGaps = Array.isArray(pdca?.gaps) ? pdca!.gaps! : [];
  const pdcaNext = Array.isArray(pdca?.next_actions) ? pdca!.next_actions! : [];

  return (
    <Shell active="/vpoint">
      <h1>Vポイント</h1>
      <p className="sub">
        月次付与サマリ（日次利用／月次条件・％別）と考察。ウィンドウC（25日〜月末）に更新。
        定期払いチャンス（テイチャン）の進捗・抽選もここに載せます。
        獲得効率は下の PDCA（良かった点／要改善）を見ながら Jarvis と進めます。
      </p>

      {pdca ? (
        <article className="card" id="pdca">
          <header>
            <span className="lvl">PDCA</span>
            <strong>獲得効率ボード</strong>
          </header>
          <p className="meta">更新 {pdca.at || "—"} · ステータス把握 → 会話で改善</p>
          {pdca.user_intent_note ? (
            <p className="sum">{pdca.user_intent_note}</p>
          ) : null}
          <div className="vpoint-rate-table-wrap" style={{ display: "grid", gap: "1rem", gridTemplateColumns: "1fr 1fr" }}>
            <div>
              <h3 className="vpoint-subh">良かった点</h3>
              <ul>
                {pdcaWins.length === 0 ? <li>—</li> : null}
                {pdcaWins.map((w) => (
                  <li key={w.id || w.title}>
                    <strong>{w.title}</strong>
                    {w.detail ? <span className="meta"> — {w.detail}</span> : null}
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <h3 className="vpoint-subh">要改善</h3>
              <ul>
                {pdcaGaps.length === 0 ? <li>—</li> : null}
                {pdcaGaps.map((g) => (
                  <li key={g.id || g.title}>
                    <strong>{g.title}</strong>
                    {g.detail ? <span className="meta"> — {g.detail}</span> : null}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          {pdcaNext.length > 0 ? (
            <>
              <h3 className="vpoint-subh">次の一手（最大2）</h3>
              <ul>
                {pdcaNext.map((n) => (
                  <li key={n.id || n.title}>
                    <strong>{n.title}</strong>
                    {n.how ? <span className="meta"> → {n.how}</span> : null}
                  </li>
                ))}
              </ul>
            </>
          ) : null}
        </article>
      ) : null}

      {showBanner && hasGrant ? (
        <article className="card level-info etc-rebate-banner">
          <header>
            <span className="lvl">付与</span>
            <strong>{target}分のポイント付与サマリ</strong>
          </header>
          <div className="etc-rebate-hero">
            <div>
              <span className="meta">合計</span>
              <strong className="etc-rebate-yen">{fmtPt(summary.total_pt)}</strong>
            </div>
            <div>
              <span className="meta">月次条件系</span>
              <strong>{fmtPt(bc.monthly ?? 0)}</strong>
            </div>
            <div>
              <span className="meta">日次・利用連動</span>
              <strong>{fmtPt(bc.daily ?? 0)}</strong>
            </div>
            <div>
              <span className="meta">その他</span>
              <strong>{fmtPt(bc.other ?? 0)}</strong>
            </div>
          </div>
          <p className="sum">
            {summary.grant_rule ||
              "ウィンドウC（25日〜月末）に月次サマリ更新。付与は日次利用と月次条件が混在"}
          </p>
          {summary.source_note ? (
            <p className="meta">{summary.source_note}</p>
          ) : null}

          {byRate.length > 0 ? (
            <div className="vpoint-rate-table-wrap">
              <h3 className="vpoint-subh">％別集計</h3>
              <table className="vpoint-rate-table">
                <thead>
                  <tr>
                    <th>還元率</th>
                    <th>ポイント</th>
                    <th>件数</th>
                    <th>代表</th>
                  </tr>
                </thead>
                <tbody>
                  {byRate.map((r, i) => (
                    <tr key={`${r.rate_pct ?? "u"}-${i}`}>
                      <td>{fmtRate(r.rate_pct)}</td>
                      <td>{fmtPt(r.pt)}</td>
                      <td>{r.count ?? "—"}</td>
                      <td className="meta">
                        {(r.samples || [])
                          .slice(0, 2)
                          .map((s) => s.desc || "")
                          .filter(Boolean)
                          .join(" / ") || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {insights.length > 0 ? (
            <div className="vpoint-insights">
              <h3 className="vpoint-subh">考察</h3>
              <ul className="etc-guide-list">
                {insights.map((ins, i) => (
                  <li key={i}>{ins}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <VpointAckButton targetMonth={target!} />
        </article>
      ) : hasGrant ? (
        <article className="card level-ok etc-rebate-banner is-acked">
          <header>
            <span className="lvl">確認済</span>
            <strong>{target}分は確認済み</strong>
          </header>
          <p className="sum">
            合計 {fmtPt(summary.total_pt)}
            {bc.monthly != null ? ` · 月次条件 ${fmtPt(bc.monthly)}` : ""}
            {bc.daily != null ? ` · 日次 ${fmtPt(bc.daily)}` : ""}
            。次の表示はウィンドウC更新後です。
          </p>
        </article>
      ) : (
        <article className="card">
          <p className="sum">
            まだ付与サマリがありません。毎月25日〜月末（ウィンドウC）に Tサイト履歴／監査から
            Jarvis が更新します。
          </p>
        </article>
      )}

      <section id="card-benefit" className="etc-guide" aria-label="年間特典ウォッチ">
        <h2>年間特典ウォッチ（Olive Infinite / Marriott Bonvoy）</h2>
        <p className="sub" style={{ marginTop: 4 }}>
          2枚の年間特典が届くペースかを見て、今月どちらに支払いを寄せるかの判断材料にします。
          決めるのはご本人です。Olive は<strong>確定値</strong>（三井住友カードの月次メール）、
          Bonvoy は <strong>Zaim 取込行の概算</strong>（アメックス画面の数字とずれます）。
          条件の金額は［確認済み／推定／要確認／未確認］を併記します。
        </p>
        {!cb || cbCards.length === 0 ? (
          <p className="empty">
            まだ年間特典のデータがありません。Mac で
            <code> jarvis_card_benefit_watch.py --refresh </code>
            のあと situation_watch → push してください。
          </p>
        ) : (
          <>
            {cbCards.map((c) => (
              <article className="card level-info" key={c.id || c.name}>
                <header>
                  <span className="lvl">{c.short}</span>
                  <strong>{c.name}</strong>
                </header>
                <p className="meta">
                  期間 {c.period_start}〜{c.period_end} · 残り{c.days_left}日（約{c.months_left}か月）
                </p>
                {c.usage_yen == null ? (
                  <p className="empty">{c.note || "実額がまだありません"}</p>
                ) : (
                  <p className="sum">
                    利用額 <strong>{fmtYen(c.usage_yen)}</strong>（
                    {c.usage_kind === "confirmed" ? "確定値" : "概算"} · {c.usage_as_of} 時点）
                    · 月ペース {fmtYen(c.pace_per_month_yen)}
                  </p>
                )}
                {c.usage_source ? (
                  <p className="meta">
                    出どころ: {c.usage_source}
                    {c.usage_caveat ? ` ／ ${c.usage_caveat}` : ""}
                  </p>
                ) : null}
                {(c.tiers || []).length > 0 ? (
                  <div className="vpoint-rate-table-wrap">
                    <table className="vpoint-rate-table">
                      <thead>
                        <tr>
                          <th>特典の線</th>
                          <th>条件の金額</th>
                          <th>達成率</th>
                          <th>あと</th>
                          <th>月あたり必要</th>
                          <th>判定</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(c.tiers || []).map((t) => (
                          <tr key={t.id || t.label}>
                            <td>
                              {t.label}
                              <br />
                              <span className="meta">{t.reward}</span>
                            </td>
                            <td>
                              {fmtYen(t.threshold_yen)}
                              <br />
                              <span className="meta">［{t.threshold_status_label}］</span>
                            </td>
                            <td>{t.achieved_pct != null ? `${t.achieved_pct}%` : "—"}</td>
                            <td>{fmtYen(t.remaining_yen)}</td>
                            <td>{fmtYen(t.need_per_month_yen)}</td>
                            <td>
                              <strong>
                                {verdictMark(t.verdict)} {t.verdict}
                              </strong>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
                {c.counts_note ? <p className="meta">集計: {c.counts_note}</p> : null}
                {c.grant_note ? <p className="meta">付与: {c.grant_note}</p> : null}
              </article>
            ))}
            <p className="sum">
              <strong>今月はこちらを使うのがおすすめ:</strong> {cb.recommendation?.line || "—"}
              （判断材料。決めるのはご本人）
            </p>
            <p className="meta">
              月ペースは期間開始からの平均。まとまった支払いがあると実態より高く出ます。{cb.scope_note}
            </p>

            <h3 className="vpoint-subh">Olive の特典履歴</h3>
            <div style={{ display: "grid", gap: "1rem", gridTemplateColumns: "1fr 1fr" }}>
              <div>
                <strong>達成済み（入会特典）</strong>
                <ul>
                  {cbGranted.length === 0 ? <li>—</li> : null}
                  {cbGranted.map((g, i) => (
                    <li key={`${g.label}-${i}`}>
                      {g.label} {fmtPt(g.pt)} — 進呈済み（{g.granted_on}）
                      <br />
                      <span className="meta">
                        集計期間 {g.period_start}〜{g.period_end}
                        {g.source ? ` · ${g.source}` : ""}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <strong>これから（継続特典）</strong>
                <ul>
                  <li>
                    {cbUpcoming?.label || "継続特典"} — 集計期間 {cbUpcoming?.period_start}〜
                    {cbUpcoming?.period_end}
                    <br />
                    <span className="meta">
                      付与: {cbUpcoming?.grant_timing || "未確認"}
                      {cbUpcoming?.mail_status
                        ? ` · ${cbUpcoming.mail_status.as_of} 時点『${cbUpcoming.mail_status.text}』`
                        : ""}
                    </span>
                  </li>
                </ul>
              </div>
            </div>

            <h3 className="vpoint-subh" id="vpoint-exit">
              Vポイントの出口
            </h3>
            {cbExits
              .filter((x) => x.featured)
              .map((x, i) => (
                <article className="card level-info" key={`f-${x.label}-${i}`}>
                  <header>
                    <span className="lvl">最優先</span>
                    <strong style={{ fontSize: "1.15em" }}>
                      ［{x.status_label}］ {x.label}
                    </strong>
                  </header>
                  {x.note ? <p className="sum">{x.note}</p> : null}
                  {(x.extra_notes || []).map((n) => (
                    <p className="sum" key={n}>
                      ［未確認］ {n}
                    </p>
                  ))}
                  <p className="meta">
                    確認日 {x.checked_on || "—"} · 出どころ: {x.source || "—"}
                  </p>
                </article>
              ))}
            <ul>
              {cbExits
                .filter((x) => !x.featured)
                .map((x, i) => (
                  <li key={`${x.label}-${i}`}>
                    <strong>［{x.status_label}］</strong> {x.label}
                    <br />
                    <span className="meta">
                      確認日 {x.checked_on || "—"} · 出どころ: {x.source || "—"}
                    </span>
                  </li>
                ))}
            </ul>
            {cbSources.length > 0 ? (
              <p className="meta">
                公式:{" "}
                {cbSources.map((u) => (
                  <span key={u}>
                    <a href={u} target="_blank" rel="noreferrer">
                      {u}
                    </a>{" "}
                  </span>
                ))}
              </p>
            ) : null}
          </>
        )}
      </section>

      <section id="teiki-barai" className="etc-guide" aria-label="定期払いチャンス">
        <h2>定期払いチャンス（テイチャン）</h2>
        <p className="sub" style={{ marginTop: 4 }}>
          対象一覧に載るだけでは紐づきません。規約同意のあと、各サービスの公式サイトで
          Olive 等へ支払い変更し、<strong>明細に金額＞0が載ってから</strong>
          お支払い履歴・抽選券に反映されます（請求確定ごろ）。
        </p>
        {!teiki ? (
          <p className="empty">
            まだテイチャン state がダッシュボードに載っていません。Mac で
            <code> jarvis_teiki_barai_chance.py --run </code>
            のあと situation_watch → push してください。
          </p>
        ) : (
          <>
            <div className="etc-rebate-hero">
              <div>
                <span className="meta">規約同意</span>
                <strong>{teiki.enrolled || "—"}</strong>
              </div>
              <div>
                <span className="meta">対象サービス</span>
                <strong>
                  {teiki.service_count != null ? `${teiki.service_count}件` : "—"}
                </strong>
              </div>
              <div>
                <span className="meta">抽選券</span>
                <strong>
                  {teiki.ticket_count != null ? `${teiki.ticket_count}枚` : "—"}
                </strong>
              </div>
              <div>
                <span className="meta">Wチャンス</span>
                <strong>
                  {teiki.w_chance_tickets != null
                    ? `${teiki.w_chance_tickets}枚`
                    : "—"}
                </strong>
              </div>
            </div>
            <p className="meta">
              確認間隔 {teiki.interval_days ?? 7}日
              {teiki.last_check_at
                ? ` · 最終確認 ${String(teiki.last_check_at).slice(0, 16)}`
                : ""}
              {teiki.last_draw_at
                ? ` · 最終抽選 ${String(teiki.last_draw_at).slice(0, 16)}`
                : ""}
            </p>
            {teiki.last_draw?.results_summary ? (
              <article className="card level-ok" style={{ marginTop: 12 }}>
                <header>
                  <span className="lvl">抽選したよ</span>
                  <strong>直近の抽選結果</strong>
                </header>
                <p className="sum">{teiki.last_draw.results_summary}</p>
                <p className="meta">
                  before {teiki.last_draw.tickets_before ?? "—"} → after{" "}
                  {teiki.last_draw.tickets_after ?? "—"}
                </p>
              </article>
            ) : null}
            {teikiServices.length > 0 ? (
              <ul className="etc-guide-list" style={{ marginTop: 12 }}>
                {teikiServices.map((s) => (
                  <li key={s.id || s.title}>
                    <strong>{s.title || s.id}</strong>
                    {" · "}
                    {statusLabel(s.status)}
                    {s.note ? <span className="meta"> — {s.note}</span> : null}
                  </li>
                ))}
              </ul>
            ) : null}
          </>
        )}
      </section>

      <section className="etc-guide" aria-label="凡例">
        <h2>日次 vs 月次条件</h2>
        <ul className="etc-guide-list">
          <li>
            <strong>月次条件系</strong> —
            投信積立カード決済特典、選べる特典／給与特典、資産運用特典など（条件達成で月1回前後）
          </li>
          <li>
            <strong>日次・利用連動</strong> — 店名＋「＋N%」などの利用ポイント
          </li>
          <li>
            <strong>％の見方</strong> — desc の＋N% 優先。積立は pt÷積立円。yen があれば
            pt÷yen
          </li>
          <li>
            詳細突合: Literature Note §6.6 / <code>jarvis-vpoint-audit.mdc</code>
          </li>
        </ul>
      </section>

      <section>
        <h2>過去の付与</h2>
        {history.length === 0 && !hasGrant ? (
          <p className="empty">履歴はまだありません</p>
        ) : (
          <ul className="etc-history-list">
            {(history.length
              ? history
              : [
                  {
                    target_month: summary.target_month,
                    total_pt: summary.total_pt,
                    by_cadence: summary.by_cadence,
                    at: summary.at,
                    source_note: summary.source_note,
                  },
                ]
            ).map((h, i) => (
              <li key={`${h.target_month || "x"}-${i}`}>
                <strong>{h.target_month || "—"}</strong>
                {" · "}
                {fmtPt(h.total_pt)}
                {h.by_cadence ? (
                  <>
                    {" · 月次 "}
                    {fmtPt(h.by_cadence.monthly ?? 0)}
                    {" · 日次 "}
                    {fmtPt(h.by_cadence.daily ?? 0)}
                  </>
                ) : null}
                {h.at ? (
                  <span className="meta">
                    {" "}
                    · 更新 {String(h.at).slice(0, 10)}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="sub" style={{ marginTop: 16 }}>
        <Link href="/situation">状況ウォッチ →</Link>
        {" · "}
        <Link href="/metrics">収支・数値 →</Link>
      </p>
    </Shell>
  );
}
