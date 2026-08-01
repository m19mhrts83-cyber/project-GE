import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";

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

  const totalMonthly = active.reduce((a, r) => a + Number(r.monthly_yen || 0), 0);
  const aiMonthly = ai.reduce((a, r) => a + Number(r.monthly_yen || 0), 0);
  const otherMonthly = totalMonthly - aiMonthly;

  const { data: meta } = await supabase
    .from("sync_meta")
    .select("key,value")
    .eq("key", "subscriptions_pushed_at");
  const pushedAt = meta?.[0]?.value;

  return (
    <Shell active="/billing">
      <h1>課金／SaaS</h1>
      <p className="sub">
        定額・従量の見える化。正本は{" "}
        <code>config/subscriptions.yaml</code>（Mac push）。不要なら解約候補を検討。
      </p>

      <div className="stats">
        <div className="stat">
          月額換算合計 <strong>{fmtYen(totalMonthly)}</strong>
        </div>
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
          最終 push: {pushedAt}
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
