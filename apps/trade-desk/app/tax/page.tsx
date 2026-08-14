import Shell from "@/components/Shell";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import TaxMetricsForm from "@/components/TaxMetricsForm";
import { createClient } from "@/lib/supabase/server";
import { corporateCycle, personalCycle } from "@/lib/taxCycle";
import {
  buildTaxYearViews,
  refundLabel,
  yearOptions,
  type TaxYearMetricRow,
} from "@/lib/taxInsights";
import type { FinanceCategoryYearRow } from "@/lib/reFinanceYtd";
import { fmtPctSigned, fmtYen, fmtYenSigned } from "@/lib/format";

export const dynamic = "force-dynamic";

type CaseRow = {
  id: string;
  fiscal_year: number;
  title: string;
  status: string;
  scope: string;
  csv_path: string | null;
};

type EvidenceRow = {
  id: string;
  fiscal_year: number;
  scope: string | null;
  doc_kind: string;
  subject: string | null;
  original_filename: string | null;
  stored_path: string;
  received_at: string | null;
};

function docKindLabel(kind: string): string {
  if (kind === "filed_return") return "確定申告書";
  if (kind === "re_statement") return "収支内訳書";
  if (kind === "attachment") return "メール添付";
  if (kind === "manual_inbox") return "手動取込";
  if (kind === "mail_note") return "メールメモ";
  return kind;
}

function primaryFiledEvidence(
  scope: string,
  year: number,
  evidence: EvidenceRow[]
): EvidenceRow | null {
  const rows = evidence.filter(
    (e) => (e.scope || "personal") === scope && e.fiscal_year === year
  );
  return (
    rows.find((e) => e.doc_kind === "filed_return") ||
    rows.find((e) => e.doc_kind === "attachment") ||
    rows[0] ||
    null
  );
}

function ingested(
  scope: "personal" | "corporate",
  year: number,
  cases: CaseRow[],
  evidence: EvidenceRow[]
): boolean {
  if (scope === "personal") {
    return cases.some(
      (c) =>
        c.scope === "personal" &&
        c.fiscal_year === year &&
        (c.status === "csv_ready" || c.status === "registered" || c.status === "closed")
    );
  }
  const ev = evidence.filter(
    (e) => e.fiscal_year === year && (e.scope || "personal") === scope
  );
  return ev.length > 0;
}

function caseReadyYears(scope: string, cases: CaseRow[]): Set<number> {
  const s = new Set<number>();
  for (const c of cases) {
    if (c.scope !== scope) continue;
    if (c.status === "csv_ready" || c.status === "registered" || c.status === "closed") {
      s.add(c.fiscal_year);
    }
  }
  return s;
}

function evidenceCounts(
  scope: string,
  evidence: EvidenceRow[]
): Map<number, number> {
  const m = new Map<number, number>();
  for (const e of evidence) {
    if ((e.scope || "personal") !== scope) continue;
    m.set(e.fiscal_year, (m.get(e.fiscal_year) ?? 0) + 1);
  }
  return m;
}

export default async function TaxPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const personal = personalCycle();
  const corporate = corporateCycle();
  const personalYears = yearOptions("personal", personal.year, 10);
  const corporateYears = yearOptions("corporate", corporate.year, 5);
  const minYear = Math.min(...personalYears, ...corporateYears);

  const [
    { data: cases },
    { data: evidence },
    { data: jobs },
    { data: metrics },
    { data: catYears },
  ] = await Promise.all([
    supabase
      .from("kurashift_tax_cases")
      .select("id, fiscal_year, title, status, scope, csv_path")
      .order("fiscal_year", { ascending: false }),
    supabase
      .from("kurashift_tax_evidence")
      .select(
        "id, fiscal_year, scope, doc_kind, subject, original_filename, stored_path, received_at"
      )
      .order("fiscal_year", { ascending: false })
      .limit(120),
    supabase
      .from("kurashift_jobs")
      .select("id, job_type, status, title, created_at, error_text")
      .like("job_type", "tax_%")
      .order("created_at", { ascending: false })
      .limit(8),
    supabase
      .from("kurashift_tax_year_metrics")
      .select("*")
      .order("fiscal_year", { ascending: false }),
    supabase
      .from("kurashift_finance_category_year")
      .select("fiscal_year, category, income_jpy, expense_jpy, net_jpy")
      .gte("fiscal_year", minYear - 1),
  ]);

  const caseRows = (cases ?? []) as CaseRow[];
  const evRows = ([...(evidence ?? [])] as EvidenceRow[]).sort((a, b) => {
    const sa = a.scope === "corporate" ? 1 : 0;
    const sb = b.scope === "corporate" ? 1 : 0;
    if (sa !== sb) return sa - sb;
    if (a.fiscal_year !== b.fiscal_year) return b.fiscal_year - a.fiscal_year;
    const ka = a.doc_kind === "filed_return" ? 0 : a.doc_kind === "re_statement" ? 1 : 2;
    const kb = b.doc_kind === "filed_return" ? 0 : b.doc_kind === "re_statement" ? 1 : 2;
    return ka - kb;
  });
  const metricRows = (metrics ?? []) as TaxYearMetricRow[];
  const categoryRows = (catYears ?? []) as FinanceCategoryYearRow[];
  const personalIn = ingested("personal", personal.year, caseRows, evRows);
  const corporateIn = ingested("corporate", corporate.year, caseRows, evRows);
  const personalHasKpi = metricRows.some(
    (m) => m.scope === "personal" && m.fiscal_year === personal.year
  );
  const corporateHasKpi = metricRows.some(
    (m) => m.scope === "corporate" && m.fiscal_year === corporate.year
  );

  const personalViews = buildTaxYearViews({
    scope: "personal",
    years: personalYears,
    metrics: metricRows,
    categoryRows,
    caseReadyYears: caseReadyYears("personal", caseRows),
    evidenceCountByYear: evidenceCounts("personal", evRows),
    inWindow: personal.window,
    currentCycleYear: personal.year,
  });
  const corporateViews = buildTaxYearViews({
    scope: "corporate",
    years: corporateYears,
    metrics: metricRows,
    categoryRows,
    caseReadyYears: caseReadyYears("corporate", caseRows),
    evidenceCountByYear: evidenceCounts("corporate", evRows),
    inWindow: corporate.window,
    currentCycleYear: corporate.year,
  });

  const metricKey = new Set(
    metricRows.map((m) => `${m.scope}:${m.fiscal_year}`)
  );

  return (
    <Shell active="/tax" email={user?.email ?? null}>
      <p className="page-kicker">② · 確定申告サイクル</p>
      <h1>確定申告</h1>
      <p className="sub">
        上は「いま回す年」、下は「過去の評価」です。個人は暦年、法人は5月期で軸を分けています。
        個人は自分で確定申告（Jarvis依頼可）。法人は税理士委託＋証憑／KPI閲覧です。
      </p>

      <div className="grid">
        <article className="card">
          <header>
            <span className="lvl">個人 · いま</span>
            <strong>{personal.label}</strong>
          </header>
          <p>
            <span className={`status-pill ${personalIn ? "ingested" : "pending"}`}>
              {personalIn ? "弥生CSV あり" : "CSV まだ"}
            </span>{" "}
            <span className={`status-pill ${personalHasKpi ? "ingested" : "pending"}`}>
              {personalHasKpi ? "結果KPI あり" : "結果KPI まだ"}
            </span>
          </p>
          <ul className="meta tax-check">
            <li>弥生CSV: {personalIn ? "済" : "未"}</li>
            <li>
              証憑: {evidenceCounts("personal", evRows).get(personal.year) ?? 0}件
            </li>
            <li>申告結果KPI: {personalHasKpi ? "済" : "未"}</li>
          </ul>
          <p className="meta">{personal.windowLabel}</p>
          {personal.window && !personalIn ? (
            <div className="card notice" style={{ marginTop: 12, marginBottom: 12 }}>
              <strong>そろそろ確定申告の季節です</strong>
              <p className="meta" style={{ marginTop: 6 }}>
                Jarvis へ: 「{personal.jarvisPrompt}」
              </p>
            </div>
          ) : (
            <p className="meta" style={{ marginTop: 8 }}>
              依頼文: 「{personal.jarvisPrompt}」
            </p>
          )}
          <EnqueueJobButton
            jobType="tax_build_yayoi_csv"
            title={`弥生CSV ${personal.year}`}
            payload={{ fiscal_year: personal.year, scope: "personal" }}
            label="弥生CSVを作る"
          />
        </article>

        <article className="card">
          <header>
            <span className="lvl">法人 · いま</span>
            <strong>{corporate.label}</strong>
          </header>
          <p>
            <span className={`status-pill ${corporateIn ? "ingested" : "pending"}`}>
              {corporateIn ? "取り込んでいる" : "取り込んでいない"}
            </span>{" "}
            <span className={`status-pill ${corporateHasKpi ? "ingested" : "pending"}`}>
              {corporateHasKpi ? "結果KPI あり" : "結果KPI まだ"}
            </span>
          </p>
          <ul className="meta tax-check">
            <li>
              証憑: {evidenceCounts("corporate", evRows).get(corporate.year) ?? 0}件
            </li>
            <li>決算KPI: {corporateHasKpi ? "済" : "未"}</li>
          </ul>
          <p className="meta">
            {corporate.windowLabel}。Knees bee 大野さんの決算PDF（年1回）
          </p>
          {corporate.window && !corporateIn ? (
            <div className="card notice" style={{ marginTop: 12, marginBottom: 12 }}>
              <strong>そろそろ取り込みます</strong>
              <p className="meta" style={{ marginTop: 6 }}>
                Jarvis へ: 「{corporate.jarvisPrompt}」
              </p>
            </div>
          ) : (
            <p className="meta" style={{ marginTop: 8 }}>
              依頼文: 「{corporate.jarvisPrompt}」
            </p>
          )}
          <EnqueueJobButton
            jobType="tax_ingest_accountant_mail"
            title={`法人メール取込 ${corporate.year}`}
            payload={{ fiscal_year: corporate.year, scope: "corporate", limit: 20 }}
            label="大野さんメールを取り込む"
          />
        </article>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <header>
          <span className="lvl">個人 · 評価</span>
          <strong>年度推移（暦年）</strong>
        </header>
        <p className="meta">
          結果KPIは申告PDF／Jarvis登録が正です。気配はZaimの不動産CF絶対値。差＝気配−確定不動産所得（第一表③）。
        </p>
        {!personalViews.some((v) => v.hasMetrics) ? (
          <div className="card notice" style={{ marginTop: 12 }}>
            <strong>まだ結果KPIがありません</strong>
            <p className="meta" style={{ marginTop: 6 }}>
              下のフォームで1年分を登録すると、税額と前年差が出ます。
            </p>
          </div>
        ) : null}
        <div className="table-scroll" style={{ marginTop: 12 }}>
          <table>
            <thead>
              <tr>
                <th>年</th>
                <th>準備</th>
                <th>申告書</th>
                <th className="num">気配・不動産CF</th>
                <th className="num">確定・不動産所得</th>
                <th className="num">差（気配−確定）</th>
                <th className="num">課税所得</th>
                <th className="num">所得税</th>
                <th>還付／納付</th>
                <th className="num">税額の前年差</th>
                <th>気づき</th>
              </tr>
            </thead>
            <tbody>
              {personalViews.map((v) => {
                const filedEv = primaryFiledEvidence("personal", v.fiscalYear, evRows);
                return (
                <tr key={`p-${v.fiscalYear}`}>
                  <td>
                    {v.label}
                    <div className="meta">
                      {v.hasMetrics ? "結果あり" : "結果なし"}
                    </div>
                  </td>
                  <td className="meta">
                    CSV {v.hasCaseReady ? "済" : "—"}
                    <br />
                    証憑 {v.evidenceCount}件
                  </td>
                  <td className="meta">
                    {filedEv ? (
                      <a href={`/tax/evidence/${filedEv.id}`}>プレビュー</a>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="num">
                    {v.prep ? fmtYenSigned(v.prep.reCf) : "—"}
                    {v.prep ? (
                      <div className="meta">気配</div>
                    ) : null}
                  </td>
                  <td className="num">
                    {fmtYenSigned(v.filedReIncome)}
                    {v.filedReIncome != null ? (
                      <div className="meta">第一表③</div>
                    ) : null}
                  </td>
                  <td className="num">
                    {fmtYenSigned(v.zaimVsFiledDiff)}
                    <div className="meta">{fmtPctSigned(v.zaimVsFiledPct)}</div>
                  </td>
                  <td className="num">{fmtYen(v.taxableIncome)}</td>
                  <td className="num">{fmtYen(v.incomeTax)}</td>
                  <td>{refundLabel(v.refundOrPay)}</td>
                  <td className="num">
                    {fmtYenSigned(v.deltaTax)}
                    <div className="meta">{fmtPctSigned(v.deltaTaxPct)}</div>
                  </td>
                  <td className="meta">
                    {v.insights.length === 0
                      ? "—"
                      : v.insights.map((t) => <div key={t}>{t}</div>)}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="meta" style={{ marginTop: 8 }}>
          {personalViews.find((v) => v.prep)?.prep?.disclaimer}
        </p>
        <header style={{ marginTop: 16 }}>
          <span className="lvl">登録</span>
          <strong>個人の申告結果</strong>
        </header>
        <TaxMetricsForm scope="personal" currentYear={personal.year} />
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <header>
          <span className="lvl">法人 · 評価</span>
          <strong>年度推移（5月期）</strong>
        </header>
        <p className="meta">
          申告作成は税理士。ここでは証憑と決算KPIの年次比較だけを見ます。個人の暦年とは混ぜません。
        </p>
        {!corporateViews.some((v) => v.hasMetrics) ? (
          <div className="card notice" style={{ marginTop: 12 }}>
            <strong>まだ決算KPIがありません</strong>
            <p className="meta" style={{ marginTop: 6 }}>
              大野さんPDFを見て下のフォームで登録するか、先にメール取込をしてください。
            </p>
          </div>
        ) : null}
        <div className="table-scroll" style={{ marginTop: 12 }}>
          <table>
            <thead>
              <tr>
                <th>期</th>
                <th>証憑</th>
                <th className="num">売上</th>
                <th className="num">経常利益</th>
                <th className="num">法人税等</th>
                <th className="num">納付</th>
                <th className="num">納付の前年差</th>
                <th>気づき</th>
              </tr>
            </thead>
            <tbody>
              {corporateViews.map((v) => {
                const filedEv = primaryFiledEvidence("corporate", v.fiscalYear, evRows);
                return (
                <tr key={`c-${v.fiscalYear}`}>
                  <td>
                    {v.label}
                    <div className="meta">
                      {v.hasMetrics ? "結果あり" : "結果なし"}
                    </div>
                  </td>
                  <td className="meta">
                    {v.evidenceCount}件
                    {filedEv ? (
                      <>
                        <br />
                        <a href={`/tax/evidence/${filedEv.id}`}>プレビュー</a>
                      </>
                    ) : null}
                  </td>
                  <td className="num">{fmtYen(v.revenue)}</td>
                  <td className="num">{fmtYen(v.ordinaryIncome)}</td>
                  <td className="num">{fmtYen(v.corporateTax)}</td>
                  <td className="num">{fmtYen(v.taxPayable)}</td>
                  <td className="num">
                    {fmtYenSigned(v.deltaTax)}
                    <div className="meta">{fmtPctSigned(v.deltaTaxPct)}</div>
                  </td>
                  <td className="meta">
                    {v.insights.length === 0
                      ? "—"
                      : v.insights.map((t) => <div key={t}>{t}</div>)}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <header style={{ marginTop: 16 }}>
          <span className="lvl">登録</span>
          <strong>法人の決算KPI</strong>
        </header>
        <TaxMetricsForm scope="corporate" currentYear={corporate.year} />
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <header>
          <span className="lvl">案件</span>
          <strong>履歴</strong>
        </header>
        <table>
          <thead>
            <tr>
              <th>区分</th>
              <th>年度</th>
              <th>タイトル</th>
              <th>状態</th>
              <th>結果KPI</th>
            </tr>
          </thead>
          <tbody>
            {caseRows.length === 0 ? (
              <tr>
                <td colSpan={5} className="meta">
                  まだ案件がありません
                </td>
              </tr>
            ) : (
              caseRows.map((c) => (
                <tr key={c.id}>
                  <td>{c.scope === "corporate" ? "法人" : "個人"}</td>
                  <td>{c.fiscal_year}</td>
                  <td>{c.title}</td>
                  <td>{c.status}</td>
                  <td>
                    {metricKey.has(`${c.scope}:${c.fiscal_year}`) ? "あり" : "—"}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <header>
          <span className="lvl">証憑</span>
          <strong>提出PDF・メール添付</strong>
        </header>
        <p className="meta" style={{ marginTop: 0 }}>
          中身の確認はプレビューです。個人の提出PDFはカタログ取込、法人は大野さんメール取込が本線です。
        </p>
        <table>
          <thead>
            <tr>
              <th>区分</th>
              <th>年度</th>
              <th>種別</th>
              <th>件名／ファイル</th>
              <th>表示</th>
            </tr>
          </thead>
          <tbody>
            {evRows.length === 0 ? (
              <tr>
                <td colSpan={5} className="meta">
                  証憑はまだありません
                </td>
              </tr>
            ) : (
              evRows.map((e) => (
                <tr key={e.id}>
                  <td>{e.scope === "corporate" ? "法人" : "個人"}</td>
                  <td>{e.fiscal_year}</td>
                  <td className="meta">{docKindLabel(e.doc_kind)}</td>
                  <td>
                    {e.subject || e.original_filename || e.doc_kind}
                    <div className="meta">{e.original_filename}</div>
                  </td>
                  <td>
                    <a href={`/tax/evidence/${e.id}`}>プレビュー</a>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <header>
          <span className="lvl">最近のジョブ</span>
          <strong>tax_*</strong>
        </header>
        <table>
          <thead>
            <tr>
              <th>状態</th>
              <th>種別</th>
              <th>タイトル</th>
              <th>作成</th>
            </tr>
          </thead>
          <tbody>
            {(jobs ?? []).length === 0 ? (
              <tr>
                <td colSpan={4} className="meta">
                  ジョブなし
                </td>
              </tr>
            ) : (
              (jobs ?? []).map((j) => (
                <tr key={j.id}>
                  <td>{j.status}</td>
                  <td>{j.job_type}</td>
                  <td>
                    {j.title}
                    {j.error_text ? (
                      <div className="meta">{j.error_text}</div>
                    ) : null}
                  </td>
                  <td className="meta">{j.created_at?.slice(0, 19)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <p className="meta" style={{ marginTop: 16 }}>
        関連:{" "}
        <a href="/realestate">不動産（個人＋法人合算CF）</a>
        {" · "}
        <a href="/lifeplan/budget?mode=annual">ライフプラン年次</a>
      </p>
    </Shell>
  );
}
