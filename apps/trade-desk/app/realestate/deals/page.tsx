import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import DealReviewActions from "@/components/DealReviewActions";
import DealInquiryActions from "@/components/DealInquiryActions";
import RealEstateLaneNav from "@/components/RealEstateLaneNav";
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
          "id, title, status, source, area, structure, price_man, yield_pct, match_score, updated_at, advice_json, summary_json"
        )
        .order("match_score", { ascending: false, nullsFirst: false })
        .order("updated_at", { ascending: false })
        .limit(80),
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
      <RealEstateLaneNav active="b-funnel" />
      <p className="page-kicker">③-B · 実行</p>
      <h1>千三つファネル</h1>
      <p className="sub">
        情報→内見→買付→融資→購入。見送りは学習。長期プラン・今狙う条件は{" "}
        <a href="/realestate/buy-plan">買い進めプラン</a>。
        「確認した」「対象外」で紐づく Gmail を既読。取込時に明らかに対象外のものは自動で見送り＋既読。
        検討を進める物件は「第一問い合わせ」（From=admin・確認後送信）。返信は蓄積し運営相談パックへ。
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
            jobType="ops_consult_ingest"
            title="運営経緯を再取込"
            label="運営経緯"
            payload={{}}
          />
          <EnqueueJobButton
            jobType="re_deal_inquiry_poll"
            title="第一問い合わせの返信を取込"
            label="返信取込"
            payload={{}}
          />
        </p>
        <p className="meta" style={{ marginTop: 8 }}>
          Excel 再取込・STEP3 export は{" "}
          <a href="/realestate/buy-plan">買い進めプラン</a> へ移動しました。
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
          現行プラン:{" "}
          <a href="/realestate/buy-plan">
            {buyPlan?.label || buyPlan?.version_key || "未取込"}
          </a>
          {" · "}
          <a href="/realestate">運用ハブ →</a>
        </p>
      </div>

      <div className="card">
        <header>
          <span className="lvl">Focus</span>
          <strong>今狙う条件（要約）</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          詳細・年表はプラン画面。ここは候補マッチ用の短冊のみ。
        </p>
        <ul className="meta" style={{ paddingLeft: 18 }}>
          {criteriaLines.length === 0 ? (
            <li>条件未取込 — プランで Excel 再取込</li>
          ) : (
            criteriaLines.slice(0, 8).map((c, i) => (
              <li key={`${c.sort_order}-${i}`}>{c.raw_text}</li>
            ))
          )}
        </ul>
        <p style={{ marginTop: 8 }}>
          <a href="/realestate/buy-plan">買い進めプランで全条件・年表を見る →</a>
        </p>
      </div>

      <div className="card">
        <header>
          <span className="lvl">運営経緯</span>
          <strong>809 ヒット（直近）</strong>
        </header>
        <ul className="meta" style={{ paddingLeft: 18, marginTop: 8 }}>
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
                <th>スコア</th>
                <th>タイトル</th>
                <th>エリア</th>
                <th>構造</th>
                <th>価格万</th>
                <th>利回</th>
                <th>助言</th>
                <th>操作</th>
                <th>第一問合せ</th>
              </tr>
            </thead>
            <tbody>
              {(deals || [])
                .filter((d) => d.status !== "archived")
                .map((d) => {
                const advice = d.advice_json as {
                  summary?: string;
                  tips?: string[];
                } | null;
                const tip =
                  advice?.summary ||
                  (advice?.tips && advice.tips[0]) ||
                  "—";
                const sj =
                  d.summary_json && typeof d.summary_json === "object"
                    ? (d.summary_json as {
                        gmail_id?: string;
                        gmail_read_at?: string;
                        from?: string;
                        inquiry_status?: string;
                        messages?: Array<{
                          direction?: string;
                          kind?: string;
                          subject?: string;
                          from_email?: string;
                          occurred_at?: string;
                          body_text?: string;
                        }>;
                      })
                    : {};
                return (
                  <tr key={d.id}>
                    <td>{STATUS_LABEL[d.status] || d.status}</td>
                    <td className="meta">
                      {d.match_score != null ? d.match_score : "—"}
                    </td>
                    <td>
                      {d.title}
                      <div className="meta">{d.source || ""}</div>
                    </td>
                    <td className="meta">{d.area || "—"}</td>
                    <td className="meta">{d.structure || "—"}</td>
                    <td className="meta">
                      {d.price_man != null ? fmtYen(Number(d.price_man) * 10000) : "—"}
                    </td>
                    <td className="meta">
                      {d.yield_pct != null
                        ? `${(Number(d.yield_pct) * 100).toFixed(1)}%`
                        : "—"}
                    </td>
                    <td className="meta">{tip}</td>
                    <td>
                      <DealReviewActions
                        dealId={d.id}
                        status={d.status}
                        gmailId={sj.gmail_id || null}
                        gmailReadAt={sj.gmail_read_at || null}
                      />
                    </td>
                    <td>
                      <DealInquiryActions
                        dealId={d.id}
                        title={d.title}
                        fromRaw={sj.from || null}
                        inquiryStatus={sj.inquiry_status || null}
                        messages={sj.messages || null}
                      />
                    </td>
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
