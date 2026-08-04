import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";
import { formatJstYmdHm } from "@/lib/formatJst";

type SubRow = {
  id: string;
  name: string;
  category: string;
  status: string;
  billing: string;
  amount_yen: number;
  monthly_yen: number;
  next_bill: string | null;
  watch: boolean;
  watch_reason: string | null;
  usage_note: string | null;
  cancel_candidate: boolean;
  billing_url: string | null;
  note: string | null;
};

type MonthlySummary = {
  as_of_ym?: string;
  prev_ym?: string | null;
  compared_at?: string;
  confirmed_at?: string | null;
  active_monthly_total?: number;
  prev_active_monthly_total?: number | null;
  delta_monthly?: number | null;
  added?: { id?: string; name?: string; monthly_yen?: number }[];
  removed?: { id?: string; name?: string }[];
  amount_changed?: {
    name?: string;
    from_monthly?: number;
    to_monthly?: number;
  }[];
  status_changed?: { name?: string; from?: string; to?: string }[];
  watch_alerts?: { name?: string; reason?: string }[];
  watch_active?: { name?: string; reason?: string }[];
  has_changes?: boolean;
};

const CAT_LABEL: Record<string, string> = {
  ai: "AI 活用",
  lifestyle: "生活・ソフト",
  telecom: "通信",
  education: "教育",
  domain_soft: "ドメイン・基盤ソフト",
  community: "コミュニティ",
  infra: "インフラ（無料枠）",
};

const STATUS_LABEL: Record<string, string> = {
  active: "継続",
  ending: "期間残・終了予定",
  ended: "終了",
  free: "無料",
  unknown: "不明",
};

const OTHER_ORDER = [
  "community",
  "education",
  "lifestyle",
  "telecom",
  "domain_soft",
];

function fmtYen(n: number | null | undefined) {
  if (n == null) return "—";
  return `${Math.round(n).toLocaleString("ja-JP")}円`;
}

function parseMonthly(raw: string | undefined): MonthlySummary | null {
  if (!raw) return null;
  try {
    const v = JSON.parse(raw) as MonthlySummary;
    return v && typeof v === "object" ? v : null;
  } catch {
    return null;
  }
}

function ServiceCard({ s }: { s: SubRow }) {
  return (
    <article className={`card${s.watch ? " level-warn" : ""}`}>
      <header>
        <span className="lvl">{STATUS_LABEL[s.status] || s.status}</span>
        <strong>{s.name}</strong>
        <span className="meta">
          {s.billing}
          {s.cancel_candidate ? " · 解約候補" : ""}
        </span>
      </header>
      <p className="sum" style={{ margin: "6px 0" }}>
        額面 {fmtYen(s.amount_yen)}
        {s.billing === "yearly" ? "（年）" : ""}
        {" → "}
        月額換算 <strong>{fmtYen(s.monthly_yen)}</strong>
        {s.next_bill ? (
          <span className="meta"> · 次回 {s.next_bill}</span>
        ) : null}
      </p>
      {s.usage_note ? <p className="meta">{s.usage_note}</p> : null}
      {s.watch_reason ? <p className="meta">注視: {s.watch_reason}</p> : null}
      {s.note ? <p className="meta">{s.note}</p> : null}
      {s.billing_url ? (
        <p className="meta">
          <a href={s.billing_url} target="_blank" rel="noopener noreferrer">
            請求・設定 ↗
          </a>
        </p>
      ) : null}
    </article>
  );
}

function MonthlySummaryBlock({ s }: { s: MonthlySummary }) {
  const ym = s.as_of_ym || "—";
  const prev = s.prev_ym || "—";
  const delta = s.delta_monthly;
  const hasPrev = Boolean(s.prev_ym);
  const deltaBadge =
    delta == null
      ? { text: "前月比なし", cls: "billing-delta-neutral" }
      : delta > 0
        ? {
            text: `前月比 +${fmtYen(delta)}`,
            cls: "billing-delta-up",
          }
        : delta < 0
          ? {
              text: `前月比 ${fmtYen(delta)}`,
              cls: "billing-delta-down",
            }
          : { text: "前月比 ±0", cls: "billing-delta-neutral" };
  const added = s.added || [];
  const removed = s.removed || [];
  const amount = s.amount_changed || [];
  const status = s.status_changed || [];
  const alerts = s.watch_alerts || [];
  const watch = s.watch_active || [];
  const noChange =
    hasPrev &&
    !added.length &&
    !removed.length &&
    !amount.length &&
    !status.length &&
    !alerts.length;
  const baselineOnly = !hasPrev;

  return (
    <section className="billing-monthly-summary card">
      <p className="billing-summary-kicker">
        確認サマリー · {ym}
        {hasPrev ? `（対比 ${prev}）` : "（ベースライン）"}
      </p>
      <div className="billing-summary-hero">
        <div>
          <p className="billing-hero-label">月額換算（継続中）</p>
          <p className="billing-hero-value">
            {fmtYen(s.active_monthly_total)}
          </p>
        </div>
        <span className={`billing-delta-badge ${deltaBadge.cls}`}>
          {baselineOnly ? "前月比なし（初回）" : deltaBadge.text}
        </span>
      </div>

      {baselineOnly ? (
        <p className="billing-summary-quiet">
          初回スナップショットです。来月以降に前月比・新規・金額変更が出ます。
        </p>
      ) : noChange ? (
        <p className="billing-summary-quiet">前月比なし（変化なし）。</p>
      ) : (
        <div className="billing-summary-sections">
          {added.length > 0 ? (
            <div className="billing-summary-sec">
              <h3>新規</h3>
              <ul>
                {added.map((x) => (
                  <li key={String(x.id || x.name)}>
                    {x.name || x.id}
                    <span className="meta"> · {fmtYen(x.monthly_yen)}/月</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {removed.length > 0 ? (
            <div className="billing-summary-sec">
              <h3>削除・除外</h3>
              <ul>
                {removed.map((x) => (
                  <li key={String(x.id || x.name)}>{x.name || x.id}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {amount.length > 0 ? (
            <div className="billing-summary-sec">
              <h3>金額変更</h3>
              <ul>
                {amount.map((x) => (
                  <li key={String(x.name)}>
                    {x.name}
                    <span className="meta">
                      {" "}
                      · {fmtYen(x.from_monthly)} → {fmtYen(x.to_monthly)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {status.length > 0 ? (
            <div className="billing-summary-sec">
              <h3>ステータス変更</h3>
              <ul>
                {status.map((x) => (
                  <li key={String(x.name)}>
                    {x.name}
                    <span className="meta">
                      {" "}
                      · {STATUS_LABEL[x.from || ""] || x.from} →{" "}
                      {STATUS_LABEL[x.to || ""] || x.to}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {alerts.length > 0 ? (
            <div className="billing-summary-sec">
              <h3>注視・新規アラート</h3>
              <ul>
                {alerts.map((x) => (
                  <li key={String(x.name)}>
                    {x.name}
                    <span className="meta"> · {x.reason || "—"}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      )}

      {watch.length > 0 ? (
        <div className="billing-summary-sec billing-summary-watch">
          <h3>注視中</h3>
          <ul>
            {watch.map((x) => (
              <li key={String(x.name)}>
                {x.name}
                {x.reason ? (
                  <span className="meta"> · {x.reason}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <p className="meta billing-summary-foot">
        最終確認:{" "}
        {s.confirmed_at ? formatJstYmdHm(s.confirmed_at) : "未確認（要確認）"}
        {s.compared_at ? ` · 差分計算 ${formatJstYmdHm(s.compared_at)}` : ""}
      </p>
    </section>
  );
}

export default async function BillingPage() {
  const supabase = await createClient();
  const { data: rows } = await supabase
    .from("subscription_services")
    .select("*")
    .order("name");

  const list = ((rows || []) as SubRow[]).slice().sort((a, b) => {
    const c = (a.category || "").localeCompare(b.category || "");
    return c !== 0 ? c : (a.name || "").localeCompare(b.name || "");
  });
  const active = list.filter((r) => r.status === "active");
  const ai = active.filter((r) => r.category === "ai");
  const watch = list.filter((r) => r.watch);
  const ending = list.filter((r) => r.status === "ending");
  const ended = list.filter((r) => r.status === "ended");

  const aiMonthly = ai.reduce((a, r) => a + Number(r.monthly_yen || 0), 0);
  const otherMonthly = active
    .filter((r) => r.category !== "ai")
    .reduce((a, r) => a + Number(r.monthly_yen || 0), 0);

  const { data: meta } = await supabase
    .from("sync_meta")
    .select("key,value")
    .in("key", ["subscriptions_pushed_at", "subscriptions_monthly_summary"]);
  const metaMap = Object.fromEntries(
    (meta || []).map((m) => [m.key, m.value as string]),
  );
  const pushedAt = metaMap.subscriptions_pushed_at;
  const monthly = parseMonthly(metaMap.subscriptions_monthly_summary);

  return (
    <Shell active="/billing">
      <h1>課金／SaaS</h1>
      <p className="sub">
        定額・従量の見える化。正本は{" "}
        <code>config/subscriptions.yaml</code>（Mac push）。月次で変更点を先頭に表示。
      </p>

      {monthly ? <MonthlySummaryBlock s={monthly} /> : (
        <p className="meta" style={{ marginBottom: 16 }}>
          月次サマリーはまだありません。Mac で{" "}
          <code>jarvis_subscriptions_push.py --push</code> を実行してください。
        </p>
      )}

      <div className="stats">
        <div className="stat">
          AI 系 <strong>{fmtYen(aiMonthly)}</strong>
        </div>
        <div className="stat">
          その他 <strong>{fmtYen(otherMonthly)}</strong>
        </div>
        <div className="stat">
          注視 <strong>{watch.length}</strong>
        </div>
      </div>
      {pushedAt ? (
        <p className="meta" style={{ marginBottom: 20 }}>
          最終 push: {formatJstYmdHm(pushedAt)}
        </p>
      ) : (
        <p className="meta" style={{ marginBottom: 20 }}>
          まだ push されていません。Mac で{" "}
          <code>jarvis_subscriptions_push.py --push</code>
        </p>
      )}

      <h2>注視（無料→有料・従量）</h2>
      {watch.length === 0 ? (
        <p className="empty">なし</p>
      ) : (
        watch.map((s) => <ServiceCard key={s.id} s={s} />)
      )}

      <h2>AI 活用でかかっているもの</h2>
      {ai.length === 0 ? (
        <p className="empty">なし</p>
      ) : (
        ai.map((s) => <ServiceCard key={s.id} s={s} />)
      )}

      <h2>その他の継続課金</h2>
      {OTHER_ORDER.map((cat) => {
        const items = active.filter((r) => r.category === cat);
        if (items.length === 0) return null;
        return (
          <div key={cat} style={{ marginBottom: 16 }}>
            <h3 style={{ fontSize: "1rem", margin: "12px 0 8px" }}>
              {CAT_LABEL[cat] || cat}
            </h3>
            {items.map((s) => (
              <ServiceCard key={s.id} s={s} />
            ))}
          </div>
        );
      })}

      <h2>解約済・期間残</h2>
      {[...ending, ...ended].length === 0 ? (
        <p className="empty">なし</p>
      ) : (
        [...ending, ...ended].map((s) => <ServiceCard key={s.id} s={s} />)
      )}
    </Shell>
  );
}
