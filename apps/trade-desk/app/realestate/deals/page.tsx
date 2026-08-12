import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import { createClient } from "@/lib/supabase/server";
import { fmtYen } from "@/lib/format";

export const dynamic = "force-dynamic";

const STATUS_LABEL: Record<string, string> = {
  info: "情報",
  viewing: "内見",
  offer: "買付",
  loan: "融資",
  purchased: "購入",
  passed: "見送り",
  archived: "アーカイブ",
};

const FUNNEL = ["info", "viewing", "offer", "loan", "purchased"] as const;

export default async function RealEstateDealsPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const [{ data: deals }, { data: criteria }, { data: ops }, { data: buyPlan }] =
    await Promise.all([
      supabase
        .from("kurashift_re_deals")
        .select(
          "id, title, status, source, area, structure, price_man, yield_pct, match_score, updated_at, advice_json"
        )
        .order("updated_at", { ascending: false })
        .limit(50),
      supabase
        .from("kurashift_buy_plan_criteria")
        .select("kind, raw_text, sort_order, version_id")
        .order("sort_order", { ascending: true })
        .limit(40),
      supabase
        .from("kurashift_ops_consult_events")
        .select("occurred_at, subject, tags, snippet")
        .order("occurred_at", { ascending: false })
        .limit(8),
      supabase
        .from("kurashift_buy_plan_versions")
        .select("id, version_key, label")
        .eq("is_canonical", true)
        .maybeSingle(),
    ]);

  const counts: Record<string, number> = {};
  for (const s of Object.keys(STATUS_LABEL)) counts[s] = 0;
  for (const d of deals || []) {
    counts[d.status] = (counts[d.status] || 0) + 1;
  }

  const canonId = buyPlan?.id;
  const criteriaLines = (criteria || []).filter(
    (c) => !canonId || c.version_id === canonId
  );

  return (
    <Shell active="/realestate" email={user?.email ?? null}>
      <p className="page-kicker">③-B · 買い進め</p>
      <h1>千三つファネル</h1>
      <p className="sub">
        情報→内見→買付→融資→購入。見送りは失敗ではなく学習。自動問い合わせ送信はしません。
        仕様: <code>docs/KURASHIFT_買い進めJob仕様.md</code>
      </p>

      <div className="card">
        <header>
          <span className="lvl">Jobs</span>
          <strong>候補の更新（Mac worker）</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          送信はしません。キュー後に Mac の{" "}
          <code>jarvis_kurashift_job_worker.py</code> が実行します。
        </p>
        <p style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 8 }}>
          <EnqueueJobButton
            jobType="re_mail_match"
            title="物件メール候補を取り込む"
            label="メール候補を更新"
            payload={{ apply: true, days: 120, limit: 40 }}
          />
          <EnqueueJobButton
            jobType="re_deal_advice"
            title="案件にQ&A助言を付与"
            label="助言を更新"
            payload={{ apply: true }}
          />
          <EnqueueJobButton
            jobType="buy_plan_ingest"
            title="買い進めExcel再取込"
            label="Excel再取込"
            payload={{}}
          />
          <EnqueueJobButton
            jobType="buy_plan_export"
            title="STEP3互換Excelをexport"
            label="STEP3 export"
            payload={{}}
          />
          <EnqueueJobButton
            jobType="ops_consult_ingest"
            title="運営経緯を再取込"
            label="運営経緯"
            payload={{}}
          />
        </p>
      </div>

      <div className="card">
        <header>
          <span className="lvl">Funnel</span>
          <strong>件数（千三つ前提）</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          {FUNNEL.map((s) => (
            <span key={s} style={{ marginRight: 12 }}>
              {STATUS_LABEL[s]} <strong>{counts[s] || 0}</strong>
            </span>
          ))}
          <span style={{ marginRight: 12 }}>
            見送り <strong>{counts.passed || 0}</strong>
          </span>
        </p>
        <p className="meta">
          現行プラン: {buyPlan?.label || buyPlan?.version_key || "未取込"}
          {" · "}
          <a href="/realestate">不動産ハブ →</a>
        </p>
      </div>

      <div className="card-grid">
        <div className="card">
          <header>
            <span className="lvl">Match</span>
            <strong>エリア・購入条件（canonical）</strong>
          </header>
          <ul className="meta" style={{ paddingLeft: 18 }}>
            {criteriaLines.length === 0 ? (
              <li>条件未取込</li>
            ) : (
              criteriaLines.slice(0, 18).map((c, i) => (
                <li key={`${c.sort_order}-${i}`}>{c.raw_text}</li>
              ))
            )}
          </ul>
        </div>
        <div className="card">
          <header>
            <span className="lvl">運営経緯</span>
            <strong>809 ヒット</strong>
          </header>
          <ul className="meta" style={{ paddingLeft: 18 }}>
            {(ops || []).length === 0 ? (
              <li>まだ無し</li>
            ) : (
              (ops || []).map((e, i) => (
                <li key={i}>
                  {(e.occurred_at || "").slice(0, 10)} · {e.subject}
                  {e.tags?.length ? `（${(e.tags as string[]).join(",")}）` : ""}
                </li>
              ))
            )}
          </ul>
        </div>
      </div>

      <div className="card">
        <header>
          <span className="lvl">Deals</span>
          <strong>案件一覧</strong>
        </header>
        {(deals || []).length === 0 ? (
          <p className="meta" style={{ marginTop: 8 }}>
            まだ案件がありません。次はメール dry-run（admin 主＋estate
            補完）で候補を載せます。Q&amp;A 助言は案件条件確定後に{" "}
            <code>advice_json</code> へ。
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>状態</th>
                <th>タイトル</th>
                <th>エリア</th>
                <th>価格万</th>
                <th>利回</th>
                <th>助言</th>
              </tr>
            </thead>
            <tbody>
              {(deals || []).map((d) => {
                const advice = d.advice_json as { summary?: string } | null;
                return (
                  <tr key={d.id}>
                    <td>{STATUS_LABEL[d.status] || d.status}</td>
                    <td>{d.title}</td>
                    <td className="meta">{d.area || "—"}</td>
                    <td className="meta">
                      {d.price_man != null ? fmtYen(Number(d.price_man) * 10000) : "—"}
                    </td>
                    <td className="meta">
                      {d.yield_pct != null
                        ? `${(Number(d.yield_pct) * 100).toFixed(1)}%`
                        : "—"}
                    </td>
                    <td className="meta">{advice?.summary || "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </Shell>
  );
}
