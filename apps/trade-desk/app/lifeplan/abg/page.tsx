import Shell from "@/components/Shell";
import LifeplanSheetsNav from "@/components/LifeplanSheetsNav";
import EnqueueJobButton from "@/components/EnqueueJobButton";
import { createClient } from "@/lib/supabase/server";
import { fmtYen } from "@/lib/format";
import {
  annualNoticeCopy,
  isAnnualLifeplanWindow,
  parseLifeplanMode,
  type LifeplanMode,
} from "@/lib/lifeplanNotices";
import { monthsElapsedInYear } from "@/lib/reFinanceYtd";
import {
  ABG_MEANING,
  CONTROL_MEANING,
  NATURE_MEANING,
  abgYearFromSnapshot,
  aggregateAbgFromCategoryYear,
  markVsTarget,
  type AbgYear,
  type FinanceCategoryYearRow,
  type Mark,
} from "@/lib/abgClassify";

export const dynamic = "force-dynamic";

type Metrics = {
  kind?: string;
  alpha_pct?: number | null;
  beta_pct?: number | null;
  gamma_pct?: number | null;
  alpha_target_pct?: number | null;
  beta_target_pct?: number | null;
  gamma_target_pct?: number | null;
  income_household_jpy?: number | null;
  expense_alpha_jpy?: number | null;
  expense_beta_jpy?: number | null;
  expense_gamma_jpy?: number | null;
  expense_delta_re_jpy?: number | null;
  targets?: {
    alpha_save_pct?: number;
    beta_living_pct?: number;
    gamma_self_pct?: number;
  };
  re19?: {
    income_jpy?: number;
    expense_jpy?: number;
    cf_jpy?: number;
    rows?: { category: string; income: number; expense: number }[];
  };
  education?: {
    expense_jpy?: number;
    share_of_household_pct?: number | null;
    rows?: { category: string; expense: number }[];
  };
  roi?: {
    re_cf_jpy?: number;
    repayment_jpy?: number;
    note?: string;
  };
  source?: string;
};

function modeIntro(mode: LifeplanMode, actualsYear: number, planYear: number) {
  if (mode === "annual") {
    return {
      heading: "年次更新モード",
      blurb: `${actualsYear}年実績の確定を受けて、${planYear}年以降のライフプランと予算を更新します（年1〜3回のうちの定例）。`,
    };
  }
  if (mode === "re_purchase") {
    return {
      heading: "不動産購入モード",
      blurb:
        "物件購入タイミングの計画更新。ローン・家賃・修繕・δ不動産CFを反映し、スナップショットを残してからルーティンを回します。",
    };
  }
  return {
    heading: "支出の見方",
    blurb:
      "暮らしの支出を αβγ と変えにくさで見るシートです。100歳計画と予算編成は上のタブから。",
  };
}

function AbgBar({
  label,
  pct,
  target,
  amount,
  mark,
}: {
  label: string;
  pct: number | null | undefined;
  target: number;
  amount?: number | null;
  mark?: Mark | null;
}) {
  const v = pct ?? 0;
  const width = Math.max(0, Math.min(100, v));
  const delta = pct == null ? null : Math.round((pct - target) * 10) / 10;
  return (
    <div style={{ marginBottom: 10 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          fontSize: 13,
        }}
      >
        <strong>
          {mark ? `${mark} ` : ""}
          {label} {pct == null ? "—" : `${pct}%`}
        </strong>
        <span className="meta">
          目標 {target}%
          {delta == null ? "" : `（${delta > 0 ? "+" : ""}${delta}pt）`}
        </span>
      </div>
      <div
        style={{
          height: 8,
          background: "rgba(0,0,0,0.08)",
          borderRadius: 4,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${width}%`,
            height: "100%",
            background: "var(--accent, #e8762a)",
          }}
        />
      </div>
      {amount != null ? (
        <div className="meta" style={{ fontSize: 12, marginTop: 2 }}>
          {fmtYen(amount)}
        </div>
      ) : null}
    </div>
  );
}

function AbgYearCard({
  year,
  periodLabel,
  data,
  targets,
}: {
  year: number;
  periodLabel: string;
  data: AbgYear | null;
  targets: { alpha: number; beta: number; gamma: number };
}) {
  return (
    <article className="card">
      <header>
        <span className="lvl">{periodLabel}</span>
        <strong>
          {year}年
          {data ? "" : "（データなし）"}
        </strong>
      </header>
      <p className="meta">
        支出合計（分母） {data ? fmtYen(data.spendTotal) : "—"}
        {data?.incomeHousehold
          ? ` · 世帯収入 ${fmtYen(data.incomeHousehold)}（参考）`
          : ""}
      </p>
      <AbgBar
        label="α 貯蓄・投資"
        pct={data?.alphaPct}
        target={targets.alpha}
        amount={data?.alpha}
        mark={markVsTarget(data?.alphaPct, targets.alpha)}
      />
      <AbgBar
        label="β 生活"
        pct={data?.betaPct}
        target={targets.beta}
        amount={data?.beta}
        mark={markVsTarget(data?.betaPct, targets.beta)}
      />
      <AbgBar
        label="γ 自己・教育"
        pct={data?.gammaPct}
        target={targets.gamma}
        amount={data?.gamma}
        mark={markVsTarget(data?.gammaPct, targets.gamma)}
      />
    </article>
  );
}

function ptDelta(
  a: number | null | undefined,
  b: number | null | undefined
): string {
  if (a == null || b == null) return "—";
  const d = Math.round((b - a) * 10) / 10;
  return `${d > 0 ? "+" : ""}${d}pt`;
}

function fmtAbgPct(n: number | null | undefined): string {
  return n == null ? "—" : `${n}%`;
}

export default async function LifeplanPage({
  searchParams,
}: {
  searchParams: Promise<{ mode?: string }>;
}) {
  const sp = await searchParams;
  const mode = parseLifeplanMode(sp.mode);
  const notice = annualNoticeCopy();
  const intro = modeIntro(mode, notice.actualsYear, notice.planYear);

  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const monthsElapsed = monthsElapsedInYear();
  const [{ data: snaps }, { data: jobs }, { data: financeCats }] =
    await Promise.all([
      supabase
        .from("kurashift_plan_snapshots")
        .select("id, label, fiscal_year, snapshot_at, metrics, notes")
        .order("snapshot_at", { ascending: false })
        .limit(20),
      supabase
        .from("kurashift_jobs")
        .select("id, job_type, status, title, created_at, finished_at, error_text")
        .like("job_type", "lifeplan_%")
        .order("created_at", { ascending: false })
        .limit(15),
      supabase
        .from("kurashift_finance_category_year")
        .select("fiscal_year, category, income_jpy, expense_jpy")
        .in("fiscal_year", [notice.actualsYear, notice.planYear])
        .limit(400),
    ]);

  const actualsSnap = (snaps ?? []).find((s) => {
    const m = s.metrics as Metrics | null;
    return m?.kind === "actuals";
  });
  const actuals = (actualsSnap?.metrics || null) as Metrics | null;

  const fiscalPayload =
    mode === "re_purchase"
      ? {
          fiscal_year: notice.planYear,
          trigger: "re_purchase",
        }
      : {
          fiscal_year: notice.actualsYear,
          trigger: mode === "annual" ? "annual" : "manual",
          plan_year: notice.planYear,
        };

  const targets = actuals?.targets || {
    alpha_save_pct: 20,
    beta_living_pct: 60,
    gamma_self_pct: 20,
  };
  const targetNums = {
    alpha: targets.alpha_save_pct ?? 20,
    beta: targets.beta_living_pct ?? 60,
    gamma: targets.gamma_self_pct ?? 20,
  };
  const catRows = (financeCats || []) as FinanceCategoryYearRow[];
  const fromCatsPrev = aggregateAbgFromCategoryYear(
    catRows,
    notice.actualsYear,
    "通年"
  );
  const yearPrev =
    fromCatsPrev.spendTotal > 0
      ? fromCatsPrev
      : abgYearFromSnapshot(notice.actualsYear, "通年", actuals) ?? fromCatsPrev;
  const yearNow = aggregateAbgFromCategoryYear(
    catRows,
    notice.planYear,
    `YTD（1〜${monthsElapsed}月）`
  );
  const hasNow = yearNow.spendTotal > 0;

  return (
    <Shell active="/lifeplan" email={user?.email ?? null}>
      <LifeplanSheetsNav current="abg" />
      <h1>{intro.heading}</h1>
      <p className="sub">{intro.blurb}</p>

      {isAnnualLifeplanWindow() && mode !== "annual" ? (
        <div className="notice">
          <strong>{notice.title}</strong>
          <p style={{ margin: "6px 0 10px" }}>{notice.body}</p>
          <a className="btn primary" href="/lifeplan/budget?mode=annual">
            年次更新を始める
          </a>
        </div>
      ) : null}

      <div className="card" style={{ marginBottom: 16 }}>
        <header>
          <span className="lvl">αβγ</span>
          <strong>支出の内訳（α＋β＋γ＝100%）</strong>
        </header>
        <p className="meta" style={{ margin: "0 0 8px" }}>
          分母は世帯収入ではなく、暮らしの支出合計です。目標は α20 / β60 / γ20。
          ここの ○△× は目標との差（±3pt / ±8pt）です。下の固定→変動の識別（変えにくさ）とは別です。δ不動産は分母に含めません。
        </p>
        <ul className="meta" style={{ margin: 0, paddingLeft: 18 }}>
          {ABG_MEANING.map((x) => (
            <li key={x.key}>
              <strong>
                {x.glyph} {x.title}
              </strong>
              {" … "}
              {x.blurb}
            </li>
          ))}
        </ul>
      </div>

      <div className="grid" style={{ marginBottom: 16 }}>
        <AbgYearCard
          year={notice.actualsYear}
          periodLabel={yearPrev?.periodLabel ?? "通年"}
          data={yearPrev}
          targets={targetNums}
        />
        <AbgYearCard
          year={notice.planYear}
          periodLabel={yearNow.periodLabel}
          data={hasNow ? yearNow : null}
          targets={targetNums}
        />
      </div>

      {actuals?.re19 || actuals?.education ? (
        <div className="grid" style={{ marginBottom: 16 }}>
          {actuals.re19 ? (
            <article className="card">
              <header>
                <span className="lvl">19不動産</span>
                <strong>
                  CF {actuals.re19.cf_jpy != null ? fmtYen(actuals.re19.cf_jpy) : "—"}
                </strong>
              </header>
              <p className="meta">
                収入{" "}
                {actuals.re19.income_jpy != null
                  ? fmtYen(actuals.re19.income_jpy)
                  : "—"}
                {" / "}支出{" "}
                {actuals.re19.expense_jpy != null
                  ? fmtYen(actuals.re19.expense_jpy)
                  : "—"}
                （αβγ分母外）
              </p>
              <ul className="meta" style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                {(actuals.re19.rows ?? []).slice(0, 6).map((r) => (
                  <li key={r.category}>
                    {r.category}: 入{fmtYen(r.income)} / 出{fmtYen(r.expense)}
                  </li>
                ))}
              </ul>
              <a href="/roi">物件ごとの ROI →</a>
            </article>
          ) : null}
          {actuals.education ? (
            <article className="card">
              <header>
                <span className="lvl">10.2 教育</span>
                <strong>
                  {actuals.education.expense_jpy != null
                    ? fmtYen(actuals.education.expense_jpy)
                    : "—"}
                </strong>
              </header>
              <p className="meta">
                世帯収入比{" "}
                {actuals.education.share_of_household_pct != null
                  ? `${actuals.education.share_of_household_pct}%`
                  : "—"}
                （γ に含む）
              </p>
              <ul className="meta" style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                {(actuals.education.rows ?? []).map((r) => (
                  <li key={r.category}>
                    {r.category}: {fmtYen(r.expense)}
                  </li>
                ))}
              </ul>
            </article>
          ) : null}
          {actuals.roi ? (
            <article className="card">
              <header>
                <span className="lvl">ROI 要約</span>
                <strong>
                  CF {actuals.roi.re_cf_jpy != null ? fmtYen(actuals.roi.re_cf_jpy) : "—"}
                </strong>
              </header>
              <p className="meta">
                明示返済{" "}
                {actuals.roi.repayment_jpy != null
                  ? fmtYen(actuals.roi.repayment_jpy)
                  : "—"}
              </p>
              <a href="/roi">物件ごとの ROI →</a>
            </article>
          ) : null}
        </div>
      ) : null}

      <div className="grid" style={{ marginBottom: 8 }}>
        <article className="card">
          <header>
            <span className="lvl">トリガー</span>
            <strong>年末〜年始</strong>
          </header>
          <p className="meta">
            12月終了後にお知らせ。年間実績確定 → 以降の LP／予算更新。
          </p>
          <a className="btn" href="/lifeplan/budget?mode=annual">
            年次更新モード
          </a>
        </article>
        <article className="card">
          <header>
            <span className="lvl">トリガー</span>
            <strong>不動産購入</strong>
          </header>
          <p className="meta">
            購入時に計画を更新。19不動産・CF・δを見直し、スナップショットを残す。
          </p>
          <a className="btn" href="/lifeplan/budget?mode=re_purchase">
            物件購入で計画更新
          </a>
        </article>
        <article className="card">
          <header>
            <span className="lvl">その他</span>
            <strong>Jarvis 相談</strong>
          </header>
          <p className="meta">
            別モードが必要になったらチャットで相談。結果は相談レーンへ。
          </p>
          <a href="/consultations">相談記録 →</a>
        </article>
      </div>

      {mode === "re_purchase" ? (
        <div className="card" style={{ marginBottom: 16 }}>
          <header>
            <span className="lvl">物件購入</span>
            <strong>まず計画スナップショット</strong>
          </header>
          <p className="meta">
            更新前の計画を残してから、下記ルーティンで CF／予算を直します。
          </p>
          <EnqueueJobButton
            jobType="lifeplan_snapshot"
            title="購入前スナップショット"
            payload={{
              fiscal_year: notice.planYear,
              trigger: "re_purchase",
              label: `re_purchase_before_${notice.planYear}`,
            }}
            label="購入前スナップを保存"
          />
        </div>
      ) : null}

      {(mode === "annual" || mode === "re_purchase") && (
        <div className="card" style={{ marginBottom: 16 }}>
          <header>
            <span className="lvl">年次更新</span>
            <strong>操作は予算編成シートへ</strong>
          </header>
          <p className="meta">
            実績反映・月別予算・100歳計画への反映は予算編成で進めます。こちらは支出内訳の確認用です。
          </p>
          <a className="btn primary" href={`/lifeplan/budget?mode=${mode}`}>
            予算編成で更新する
          </a>
        </div>
      )}

      {mode === "default" ? (
        <div className="card" style={{ marginTop: 8 }}>
          <p className="meta" style={{ margin: 0 }}>
            上のトリガーからモードを選ぶと、4段階ルーティンが表示されます。トップ画面の主戦場はテーマ投資です。
          </p>
        </div>
      ) : null}

      <div className="card" style={{ marginTop: 20 }}>
        <header>
          <span className="lvl">比較</span>
          <strong>
            {notice.actualsYear}通年 vs {notice.planYear} YTD（支出比）
          </strong>
        </header>
        <p className="meta">
          ％は αβγ 支出合計に対する内訳なので、年の途中でも並べられます。金額は期間が違います。
        </p>
        <table>
          <thead>
            <tr>
              <th>項目</th>
              <th>目標</th>
              <th>{notice.actualsYear} 通年</th>
              <th>
                {notice.planYear} YTD（1〜{monthsElapsed}月）
              </th>
              <th>差</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>α 貯蓄・投資</td>
              <td>{targetNums.alpha}%</td>
              <td>
                {markVsTarget(yearPrev.alphaPct, targetNums.alpha) ?? ""}{" "}
                {fmtAbgPct(yearPrev.alphaPct)}
              </td>
              <td>
                {hasNow
                  ? `${markVsTarget(yearNow.alphaPct, targetNums.alpha) ?? ""} ${fmtAbgPct(yearNow.alphaPct)}`
                  : "—"}
              </td>
              <td>{hasNow ? ptDelta(yearPrev.alphaPct, yearNow.alphaPct) : "—"}</td>
            </tr>
            <tr>
              <td>β 生活</td>
              <td>{targetNums.beta}%</td>
              <td>
                {markVsTarget(yearPrev.betaPct, targetNums.beta) ?? ""}{" "}
                {fmtAbgPct(yearPrev.betaPct)}
              </td>
              <td>
                {hasNow
                  ? `${markVsTarget(yearNow.betaPct, targetNums.beta) ?? ""} ${fmtAbgPct(yearNow.betaPct)}`
                  : "—"}
              </td>
              <td>{hasNow ? ptDelta(yearPrev.betaPct, yearNow.betaPct) : "—"}</td>
            </tr>
            <tr>
              <td>γ 自己・教育</td>
              <td>{targetNums.gamma}%</td>
              <td>
                {markVsTarget(yearPrev.gammaPct, targetNums.gamma) ?? ""}{" "}
                {fmtAbgPct(yearPrev.gammaPct)}
              </td>
              <td>
                {hasNow
                  ? `${markVsTarget(yearNow.gammaPct, targetNums.gamma) ?? ""} ${fmtAbgPct(yearNow.gammaPct)}`
                  : "—"}
              </td>
              <td>{hasNow ? ptDelta(yearPrev.gammaPct, yearNow.gammaPct) : "—"}</td>
            </tr>
            <tr>
              <td>支出合計（分母）</td>
              <td className="meta">—</td>
              <td>{fmtYen(yearPrev.spendTotal)}</td>
              <td>{hasNow ? fmtYen(yearNow.spendTotal) : "—"}</td>
              <td className="meta">金額は期間が違う</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <header>
          <span className="lvl">固定 → 変動</span>
          <strong>変えにくさ（× → △ → ○）</strong>
        </header>
        <p className="meta" style={{ margin: "0 0 8px" }}>
          αβγ の支出だけを分解します（δ不動産は含めない）。ここの記号は目標達成度ではなく、手を付ける順番です。
        </p>
        <ul className="meta" style={{ margin: "0 0 12px", paddingLeft: 18 }}>
          {CONTROL_MEANING.map((x) => (
            <li key={x.mark}>
              <strong>
                {x.mark} {x.title}
              </strong>
              {" … "}
              {x.blurb}
            </li>
          ))}
        </ul>
        <table>
          <thead>
            <tr>
              <th>識別</th>
              <th>{notice.actualsYear} 通年</th>
              <th>
                {notice.planYear} YTD（1〜{monthsElapsed}月）
              </th>
              <th>差</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>× 変更困難（しない）</td>
              <td>
                {fmtAbgPct(yearPrev.controlHardPct)}（{fmtYen(yearPrev.controlHard)}）
              </td>
              <td>
                {hasNow
                  ? `${fmtAbgPct(yearNow.controlHardPct)}（${fmtYen(yearNow.controlHard)}）`
                  : "—"}
              </td>
              <td>
                {hasNow
                  ? ptDelta(yearPrev.controlHardPct, yearNow.controlHardPct)
                  : "—"}
              </td>
            </tr>
            <tr>
              <td>△ 固定費削減検討の価値あり</td>
              <td>
                {fmtAbgPct(yearPrev.controlReviewPct)}（
                {fmtYen(yearPrev.controlReview)}）
              </td>
              <td>
                {hasNow
                  ? `${fmtAbgPct(yearNow.controlReviewPct)}（${fmtYen(yearNow.controlReview)}）`
                  : "—"}
              </td>
              <td>
                {hasNow
                  ? ptDelta(yearPrev.controlReviewPct, yearNow.controlReviewPct)
                  : "—"}
              </td>
            </tr>
            <tr>
              <td>○ 予算見て削減可能</td>
              <td>
                {fmtAbgPct(yearPrev.controlFlexPct)}（{fmtYen(yearPrev.controlFlex)}）
              </td>
              <td>
                {hasNow
                  ? `${fmtAbgPct(yearNow.controlFlexPct)}（${fmtYen(yearNow.controlFlex)}）`
                  : "—"}
              </td>
              <td>
                {hasNow
                  ? ptDelta(yearPrev.controlFlexPct, yearNow.controlFlexPct)
                  : "—"}
              </td>
            </tr>
          </tbody>
        </table>
        <p className="meta" style={{ margin: "12px 0 8px" }}>
          参考：Zaim の F / C / S（会計上の出方）。識別の ×△○ とは1対1ではありません。
        </p>
        <ul className="meta" style={{ margin: "0 0 8px", paddingLeft: 18 }}>
          {NATURE_MEANING.map((x) => (
            <li key={x.key}>
              <strong>
                {x.code} {x.title}
              </strong>
              {" … "}
              {x.blurb}
            </li>
          ))}
        </ul>
        <table>
          <thead>
            <tr>
              <th>費目コード</th>
              <th>{notice.actualsYear} 通年</th>
              <th>
                {notice.planYear} YTD（1〜{monthsElapsed}月）
              </th>
              <th>差</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>F 固定</td>
              <td>
                {fmtAbgPct(yearPrev.fixedPct)}（{fmtYen(yearPrev.fixed)}）
              </td>
              <td>
                {hasNow
                  ? `${fmtAbgPct(yearNow.fixedPct)}（${fmtYen(yearNow.fixed)}）`
                  : "—"}
              </td>
              <td>{hasNow ? ptDelta(yearPrev.fixedPct, yearNow.fixedPct) : "—"}</td>
            </tr>
            <tr>
              <td>C 変動</td>
              <td>
                {fmtAbgPct(yearPrev.variablePct)}（{fmtYen(yearPrev.variable)}）
              </td>
              <td>
                {hasNow
                  ? `${fmtAbgPct(yearNow.variablePct)}（${fmtYen(yearNow.variable)}）`
                  : "—"}
              </td>
              <td>
                {hasNow ? ptDelta(yearPrev.variablePct, yearNow.variablePct) : "—"}
              </td>
            </tr>
            <tr>
              <td>S スペシャル</td>
              <td>
                {fmtAbgPct(yearPrev.spotPct)}（{fmtYen(yearPrev.spot)}）
              </td>
              <td>
                {hasNow
                  ? `${fmtAbgPct(yearNow.spotPct)}（${fmtYen(yearNow.spot)}）`
                  : "—"}
              </td>
              <td>{hasNow ? ptDelta(yearPrev.spotPct, yearNow.spotPct) : "—"}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <header>
          <span className="lvl">スナップショット</span>
          <strong>計画の時点一覧</strong>
        </header>
        <EnqueueJobButton
          jobType="lifeplan_snapshot"
          title="今の計画を保存"
          payload={{
            fiscal_year: notice.planYear,
            trigger: mode,
          }}
        />
        <table>
          <thead>
            <tr>
              <th>種別</th>
              <th>ラベル</th>
              <th>年度</th>
              <th>日付</th>
              <th>メモ</th>
            </tr>
          </thead>
          <tbody>
            {(snaps ?? []).length === 0 ? (
              <tr>
                <td colSpan={5} className="meta">
                  まだありません
                </td>
              </tr>
            ) : (
              (snaps ?? []).map((r) => {
                const m = r.metrics as Metrics | null;
                return (
                  <tr key={r.id}>
                    <td>{m?.kind ?? "—"}</td>
                    <td>{r.label}</td>
                    <td>{r.fiscal_year ?? "—"}</td>
                    <td>{r.snapshot_at}</td>
                    <td className="meta">{r.notes ?? "—"}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <header>
          <span className="lvl">最近のジョブ</span>
          <strong>lifeplan_*</strong>
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
                  <td>{j.title}</td>
                  <td className="meta">{j.created_at?.slice(0, 19)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
