import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";
import { fmtYen } from "@/lib/format";

export const dynamic = "force-dynamic";

type Roi = {
  re_cf_jpy?: number;
  repayment_jpy?: number;
  note?: string;
};

type Re19 = {
  income_jpy?: number;
  expense_jpy?: number;
  cf_jpy?: number;
  rows?: { category: string; income: number; expense: number }[];
};

type Metrics = {
  kind?: string;
  fiscal_year?: number;
  roi?: Roi;
  re19?: Re19;
  income_household_jpy?: number | null;
};

export default async function RoiPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: snaps } = await supabase
    .from("kurashift_plan_snapshots")
    .select("id, label, fiscal_year, snapshot_at, metrics")
    .order("snapshot_at", { ascending: false })
    .limit(20);

  const actuals = (snaps ?? []).find((s) => (s.metrics as Metrics | null)?.kind === "actuals");
  const m = (actuals?.metrics || null) as Metrics | null;
  const roi = m?.roi;
  const re19 = m?.re19;

  return (
    <Shell active="/roi" email={user?.email ?? null}>
      <h1>ROI（CF／返済）</h1>
      <p className="sub">
        大きな買い物・不動産の振り返り用。δ不動産のキャッシュフローと明示返済を横並び。
      </p>

      {!m ? (
        <div className="card">
          <p className="meta" style={{ margin: 0 }}>
            実績スナップがありません。ライフプラン Step1 で取込後に表示されます。
          </p>
          <a href="/lifeplan?mode=annual">ライフプランへ →</a>
        </div>
      ) : (
        <>
          <div className="grid">
            <article className="card">
              <header>
                <span className="lvl">CF</span>
                <strong>
                  {roi?.re_cf_jpy != null ? fmtYen(roi.re_cf_jpy) : "—"}
                </strong>
              </header>
              <p className="meta">
                19収入 − 19支出（{actuals?.fiscal_year}年実績）
              </p>
            </article>
            <article className="card">
              <header>
                <span className="lvl">返済（明示行）</span>
                <strong>
                  {roi?.repayment_jpy != null ? fmtYen(roi.repayment_jpy) : "—"}
                </strong>
              </header>
              <p className="meta">奨学金・ローン表記カテゴリの支出合計</p>
            </article>
            <article className="card">
              <header>
                <span className="lvl">CF − 明示返済</span>
                <strong>
                  {roi?.re_cf_jpy != null && roi?.repayment_jpy != null
                    ? fmtYen(roi.re_cf_jpy - roi.repayment_jpy)
                    : "—"}
                </strong>
              </header>
              <p className="meta">{roi?.note}</p>
            </article>
          </div>

          <div className="card" style={{ marginTop: 16 }}>
            <header>
              <span className="lvl">19不動産</span>
              <strong>内訳</strong>
            </header>
            <p className="meta">
              収入 {re19?.income_jpy != null ? fmtYen(re19.income_jpy) : "—"}
              {" / "}支出{" "}
              {re19?.expense_jpy != null ? fmtYen(re19.expense_jpy) : "—"}
            </p>
            <table>
              <thead>
                <tr>
                  <th>カテゴリ</th>
                  <th>収入</th>
                  <th>支出</th>
                </tr>
              </thead>
              <tbody>
                {(re19?.rows ?? []).length === 0 ? (
                  <tr>
                    <td colSpan={3} className="meta">
                      行なし
                    </td>
                  </tr>
                ) : (
                  (re19?.rows ?? []).map((r) => (
                    <tr key={r.category}>
                      <td>{r.category}</td>
                      <td>{fmtYen(r.income)}</td>
                      <td>{fmtYen(r.expense)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Shell>
  );
}
