import Shell from "@/components/Shell";
import { createClient } from "@/lib/supabase/server";
import { fmtYen, fmtYenSigned } from "@/lib/format";
import { loadLiabilityRates } from "@/lib/liabilityRates";
import {
  completeMonthsElapsed,
  tokyoYmd,
} from "@/lib/reFinanceYtd";
import {
  SPECIAL_LABEL,
  composeReSteadyBoard,
} from "@/lib/reSteadyCf";
import type { PropertyUnitRow } from "@/lib/roiAssets";

export const dynamic = "force-dynamic";

export default async function RealEstatePage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { year: calendarYear } = tokyoYmd();
  const actualsYear = calendarYear - 1;
  const throughMonth = completeMonthsElapsed();
  const liabilityRates = loadLiabilityRates();

  const { data: yearSnap } = await supabase
    .from("kurashift_plan_snapshots")
    .select("fiscal_year, snapshot_at, metrics, label")
    .eq("fiscal_year", actualsYear)
    .order("snapshot_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  let latestSnap = yearSnap;
  if (!latestSnap) {
    const { data: anySnap } = await supabase
      .from("kurashift_plan_snapshots")
      .select("fiscal_year, snapshot_at, metrics, label")
      .order("snapshot_at", { ascending: false })
      .limit(8);
    latestSnap =
      (anySnap || []).find((s) => {
        const m = s.metrics as { re19?: unknown } | null;
        return Boolean(m?.re19);
      }) ?? null;
  }

  const re19 = (latestSnap?.metrics as { re19?: { income_jpy?: number; expense_jpy?: number; cf_jpy?: number } } | null)
    ?.re19;

  const [{ data: unitRows }, { data: buyPlan }, { data: dealRows }, { data: reTxns }] =
    await Promise.all([
      supabase
        .from("property_units")
        .select("property_id, property_name, room, status, rent, note, payload"),
      supabase
        .from("kurashift_buy_plan_versions")
        .select("version_key, label, as_of, metadata")
        .eq("is_canonical", true)
        .maybeSingle(),
      supabase.from("kurashift_re_deals").select("status"),
      supabase
        .from("kurashift_finance_transactions")
        .select("category, subcategory, txn_date, income_jpy, expense_jpy")
        .eq("fiscal_year", calendarYear)
        .or("category.ilike.%19%,category.ilike.%賃貸%,category.ilike.%家賃%")
        .limit(4000),
    ]);

  const unitCount = unitRows?.length ?? 0;
  const reBoard = composeReSteadyBoard(
    reTxns ?? [],
    (unitRows ?? []) as PropertyUnitRow[],
    calendarYear,
    throughMonth
  );

  const funnelOrder = [
    "info",
    "viewing",
    "offer",
    "loan",
    "purchased",
    "passed",
  ] as const;
  const funnelCounts: Record<string, number> = {};
  for (const s of funnelOrder) funnelCounts[s] = 0;
  for (const d of dealRows || []) {
    const st = d.status as string;
    funnelCounts[st] = (funnelCounts[st] || 0) + 1;
  }

  const CF_GOAL_MONTH = 500_000;
  const cfAnnual = typeof re19?.cf_jpy === "number" ? re19.cf_jpy : null;
  const assumedGap = CF_GOAL_MONTH - reBoard.assumedCfMonth;

  return (
    <Shell active="/realestate" email={user?.email ?? null}>
      <h1>不動産賃貸経営</h1>
      <p className="sub">
        第3の柱。レーンは<strong>4本</strong> — ①運用・計画進捗 ②新規購入検討
        ③保有物件マスタ ④融資提出パック（段階実装中）。長期目標は{" "}
        <strong>CF 月50万円</strong>（個人＋法人合算・定義は正規化メモ）。
      </p>

      <div className="card notice">
        <header>
          <span className="lvl">③-A</span>
          <strong>
            想定と実のキャッシュフロー（{calendarYear}・{reBoard.throughLabel}）
          </strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          満室想定はレントロール年収−返済。実の定常はローン・管理・毎月経費だけ。
          取得税・固都税・修繕・年払い保険は特別支出に分けます。
          {reBoard.liveTotal > 0
            ? ` 現況 ${reBoard.liveOccupied}/${reBoard.liveTotal}戸。`
            : ""}
        </p>
        <table>
          <tbody>
            <tr>
              <td>想定CF（満室）</td>
              <td>
                <strong>{fmtYen(Math.round(reBoard.assumedCfMonth))}/月</strong>
                <span className="meta">
                  {" "}
                  · 家賃 {fmtYen(Math.round(reBoard.assumedRentMonth))} − 返済{" "}
                  {fmtYen(Math.round(reBoard.assumedPayMonth))}
                </span>
              </td>
            </tr>
            <tr>
              <td>実CF（定常）</td>
              <td>
                <strong>
                  {reBoard.steadyCfMonth != null
                    ? `${fmtYen(Math.round(reBoard.steadyCfMonth))}/月`
                    : "—"}
                </strong>
                <span className="meta">
                  {reBoard.actualRentMonth != null
                    ? ` · 実家賃 ${fmtYen(Math.round(reBoard.actualRentMonth))} − 返済 ${fmtYen(Math.round(reBoard.actualLoanMonth ?? 0))} − 経費 ${fmtYen(Math.round(reBoard.actualOpexMonth ?? 0))}`
                    : ""}
                </span>
              </td>
            </tr>
            <tr>
              <td>家賃の差（空室・未入金・NET）</td>
              <td>
                {reBoard.rentGapMonth != null
                  ? fmtYenSigned(Math.round(reBoard.rentGapMonth))
                  : "—"}
                <span className="meta">
                  {reBoard.liveOccupied === reBoard.liveTotal &&
                  reBoard.liveTotal > 0
                    ? " · いま満室。差はキャンペーン賃料・管理会社差引後・入金タイミング"
                    : " · 想定家賃 − 財務の実家賃"}
                </span>
              </td>
            </tr>
            <tr>
              <td>会計の月次（特別込み）</td>
              <td>
                {reBoard.accountingCfMonth != null
                  ? fmtYen(Math.round(reBoard.accountingCfMonth))
                  : "—"}
                <span className="meta">
                  {" "}
                  · ここがマイナスでも、一時費用の割り戻しであることが多い
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card">
        <header>
          <span className="lvl">特別支出のカバー</span>
          <strong>
            {reBoard.coverShortfall == null
              ? "—"
              : reBoard.coverShortfall <= 0
                ? "年換算定常CFで賄える"
                : `不足 ${fmtYen(Math.round(reBoard.coverShortfall))}`}
          </strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          定常月次 × 12 ={" "}
          {reBoard.annualSteady != null
            ? fmtYen(Math.round(reBoard.annualSteady))
            : "—"}
          。{reBoard.throughLabel}の特別支出合計{" "}
          {fmtYen(Math.round(reBoard.specialYtd))}
          {reBoard.coverRatio != null
            ? ` · カバー率 ${Math.round(reBoard.coverRatio * 100)}%`
            : ""}
          。
        </p>
        {reBoard.specials.length > 0 ? (
          <table>
            <tbody>
              {reBoard.specials.map((s) => (
                <tr key={s.kind}>
                  <td>{SPECIAL_LABEL[s.kind]}</td>
                  <td className="num">{fmtYen(Math.round(s.yen))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="meta">特別支出はまだ集計されていません。</p>
        )}
      </div>

      <div className="card" style={{ borderColor: "var(--accent, #c45c26)" }}>
        <header>
          <span className="lvl">目標</span>
          <strong>CF 月50万円</strong>
        </header>
        <table>
          <tbody>
            <tr>
              <td>想定（満室）とのギャップ</td>
              <td>
                <strong>{fmtYen(Math.round(assumedGap))}</strong>
              </td>
            </tr>
            <tr>
              <td>定常とのギャップ</td>
              <td>
                {reBoard.steadyCfMonth != null
                  ? fmtYen(Math.round(CF_GOAL_MONTH - reBoard.steadyCfMonth))
                  : "—"}
              </td>
            </tr>
            <tr>
              <td>LP前年（参考）</td>
              <td>{cfAnnual != null ? fmtYen(cfAnnual) : "—"}</td>
            </tr>
            <tr>
              <td>買い進め Excel</td>
              <td>
                {buyPlan
                  ? `${buyPlan.label || buyPlan.version_key}（${buyPlan.as_of}）`
                  : "未取込"}
              </td>
            </tr>
          </tbody>
        </table>
        <p className="meta" style={{ marginTop: 8 }}>
          詳細: <code>docs/KURASHIFT_CF正規化メモ.md</code>
          {" · "}
          <a href="/roi">物件ごとの満室CF →</a>
          {" · "}
          <a href="/realestate/deals">千三つファネル →</a>
        </p>
      </div>

      <div className="card notice">
        <header>
          <span className="lvl">Phase 0</span>
          <strong>4レーン方針をプランに反映済み</strong>
        </header>
        <p className="meta">
          詳細: <code>docs/KURASHIFT_不動産賃貸経営.md</code>
          {" · "}
          <code>docs/KURASHIFT_買い進めJob仕様.md</code>
        </p>
      </div>

      <div className="card">
        <header>
          <span className="lvl">返済戦略</span>
          <strong>正味の利率（イメージ）</strong>
        </header>
        <p className="meta">
          物件の収支利回り（％）− ローン金利（％）≈ 正味。利子が高い負債から返す判断に使う。
          保険の契約者貸付利率は <a href="/portfolio">資産</a> を参照。
        </p>
        <p className="meta" style={{ marginTop: 8 }}>
          {liabilityRates.realEstateNote}
        </p>
        <p className="meta">
          借入残高トラッカー連携（③-C）後に物件ごとの利回り／金利／正味を一覧化する予定。
          （
          <a
            href="https://loan-tracker-plum.vercel.app/"
            target="_blank"
            rel="noreferrer"
          >
            loan-tracker
          </a>
          ）
        </p>
      </div>

      <div className="card-grid">
        <div className="card">
          <header>
            <span className="lvl">③-A</span>
            <strong>運用・計画進捗</strong>
          </header>
          <p>
            <strong>今持っている資産</strong>が、年間計画に対して現在どうか（YTD・差分・補正）。
          </p>
          <ul className="meta">
            <li>個人／法人／合算切替</li>
            <li>実績 → 計画 → 進捗 → ギャップ → 補正</li>
            <li>入口: このページ（将来の既定タブ）</li>
          </ul>
        </div>

        <div className="card">
          <header>
            <span className="lvl">③-B</span>
            <strong>新規購入検討</strong>
          </header>
          <p>
            <strong>これから買う物件</strong>の検討を案件としてまとめる（千三つファネル）。
          </p>
          <ul className="meta">
            <li>
              情報 {funnelCounts.info} · 内見 {funnelCounts.viewing} · 買付{" "}
              {funnelCounts.offer} · 融資 {funnelCounts.loan} · 購入{" "}
              {funnelCounts.purchased} · 見送り {funnelCounts.passed}
            </li>
            <li>取得後 → ③-A の計画へ／LP 物件購入モード</li>
            <li>
              入口: <a href="/realestate/deals">/realestate/deals</a>
            </li>
          </ul>
        </div>
      </div>

      <div className="card-grid">
        <div className="card">
          <header>
            <span className="lvl">③-C</span>
            <strong>保有物件マスタ</strong>
          </header>
          <p>
            <strong>今所有している物件</strong>の基本情報。ローンは
            <a
              href="https://loan-tracker-plum.vercel.app/"
              target="_blank"
              rel="noreferrer"
            >
              借入残高トラッカー
            </a>
            を正本として連携（二重入力しない）。
          </p>
          <ul className="meta">
            <li>法人／個人の物件一覧</li>
            <li>既存: property_units・property_info.yaml</li>
            <li>
              入口: <a href="/realestate/properties">/realestate/properties</a>
            </li>
          </ul>
        </div>

        <div className="card">
          <header>
            <span className="lvl">③-D</span>
            <strong>融資提出パック</strong>
          </header>
          <p>
            融資時の<strong>提出書類一覧</strong>。必要事項を入力し、
            <strong>銀行向けに出力</strong>。
          </p>
          <ul className="meta">
            <li>書類 × 状態 × 入力フィールドの表</li>
            <li>③-C・240_融資・法人情報を参照</li>
            <li>
              入口:{" "}
              <a href="/realestate/finance-pack">/realestate/finance-pack</a>
              （チェックリスト骨格）
            </li>
          </ul>
        </div>
      </div>

      <div className="card-grid">
        <div className="card">
          <header>
            <span className="lvl">Theme</span>
            <strong>大きな判断</strong>
          </header>
          <p>
            修繕・借換え・売却（③-A）／新規取得（③-B）は Theme 承認フロー（レーン{" "}
            <code>realestate</code>）。
          </p>
          <a className="btn secondary" href="/themes">
            テーマ一覧へ
          </a>
        </div>
      </div>

      <div className="card">
        <header>
          <span className="lvl">Bridge</span>
          <strong>いま見えるデータ（個人・LP スナップ）</strong>
        </header>
        {latestSnap && re19 ? (
          <table>
            <tbody>
              <tr>
                <td>スナップ</td>
                <td>
                  {latestSnap.label}（{latestSnap.snapshot_at}）
                </td>
              </tr>
              <tr>
                <td>19不動産 収入</td>
                <td>{fmtYen(re19.income_jpy ?? 0)}</td>
              </tr>
              <tr>
                <td>19不動産 支出</td>
                <td>{fmtYen(re19.expense_jpy ?? 0)}</td>
              </tr>
              <tr>
                <td>CF（収入−支出）</td>
                <td>
                  <strong>{fmtYen(re19.cf_jpy ?? 0)}</strong>
                </td>
              </tr>
              <tr>
                <td>登録号室（稼働参考）</td>
                <td>{unitCount ?? 0} 件</td>
              </tr>
            </tbody>
          </table>
        ) : (
          <p className="meta">
            {actualsYear}{" "}
            年度（実績年）の LP スナップがありません。{" "}
            <a href="/lifeplan?mode=annual">ライフプラン</a>
            で Step1「年度実績を取り込む」を実行すると 19不動産の橋渡し表示が出ます。
          </p>
        )}
        <p className="meta" style={{ marginTop: "0.75rem" }}>
          関連: <a href="/lifeplan?mode=re_purchase">物件購入モード</a>
          {" · "}
          <a href="/roi">ROI（物件ごと）</a>
        </p>
      </div>
    </Shell>
  );
}

