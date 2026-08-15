import Shell from "@/components/Shell";
import MqBsPanel from "@/components/MqBsPanel";
import MqCompareBars from "@/components/MqCompareBars";
import MqFactsForm from "@/components/MqFactsForm";
import MqPlanForm from "@/components/MqPlanForm";
import MqZaimIngestPanel from "@/components/MqZaimIngestPanel";
import MqStrackPanel from "@/components/MqStrackPanel";
import { fmtYen } from "@/lib/format";
import {
  aggregatePlanAnnual,
  aggregateRows,
  availableMonths,
  availableYears,
  entityLabel,
  filterFactsMonth,
  filterFactsYearActual,
  filterPlans,
  lineLabel,
  listPlanVariants,
  metricBars,
  scaleAnnualComputedToMonth,
  type CompareMode,
  type EntityFilter,
  type GrainFilter,
  type LineFilter,
  type MqFactRow,
} from "@/lib/mqAggregate";
import {
  combineBs,
  monthEndDate,
  normalizeBs,
  pickNearestBs,
  yearEndDate,
  type MqBsRow,
} from "@/lib/mqBs";
import type { MqComputed } from "@/lib/mqEquations";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

type Sp = Record<string, string | string[] | undefined>;

function one(sp: Sp, key: string, fallback: string): string {
  const v = sp[key];
  if (Array.isArray(v)) return v[0] || fallback;
  return v || fallback;
}

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

type Panel = {
  title: string;
  computed: MqComputed | null;
  cashIn?: number | null;
  cashOut?: number | null;
  cashEnd?: number | null;
  depreciation?: number | null;
  emptyHint: string;
  fNote?: string;
};

export default async function MqPage({
  searchParams,
}: {
  searchParams: Promise<Sp>;
}) {
  const sp = await searchParams;
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  const line = one(sp, "line", "realestate") as LineFilter;
  const entity = one(sp, "entity", "combined") as EntityFilter;
  const grain = one(sp, "grain", "month") as GrainFilter;
  const mode = one(sp, "mode", "aa") as CompareMode;

  const { data: raw, error } = await supabase
    .from("kurashift_mq_period_facts")
    .select("*")
    .order("period_month", { ascending: false })
    .limit(500);

  const { data: bsRaw } = await supabase
    .from("kurashift_mq_bs_snapshots")
    .select("*")
    .order("as_of_date", { ascending: false })
    .limit(200);

  const rows = (raw ?? []) as MqFactRow[];
  const bsRows = (bsRaw ?? []) as MqBsRow[];
  const months = availableMonths(rows);
  const years = availableYears(rows);
  const defaultMonth = months[0] || currentMonth();
  const defaultYear = years[0] || String(new Date().getFullYear());
  const variants = listPlanVariants(rows);
  const defaultVariant = variants[0] || "基本";

  const periodA =
    grain === "year"
      ? one(sp, "a", defaultYear).slice(0, 4)
      : one(sp, "a", defaultMonth).slice(0, 7);
  const periodB =
    grain === "year"
      ? one(sp, "b", years[1] || defaultYear).slice(0, 4)
      : one(sp, "b", months[1] || defaultMonth).slice(0, 7);
  const planYear = one(sp, "py", periodA.length === 4 ? periodA : periodA.slice(0, 4));
  const variantA = one(sp, "va", defaultVariant);
  const variantB = one(sp, "vb", variants[1] || defaultVariant);

  function buildActual(period: string) {
    const subset =
      grain === "year"
        ? filterFactsYearActual(rows, line, entity, period)
        : filterFactsMonth(rows, line, entity, period);
    return aggregateRows(subset, grain === "year" ? "year" : "month");
  }

  function buildPlan(year: string, variant: string, asMonth: boolean) {
    const subset = filterPlans(rows, line, entity, year, variant);
    const ann = aggregatePlanAnnual(subset);
    if (!ann.computed) {
      return {
        ...ann,
        computed: null as MqComputed | null,
      };
    }
    return {
      ...ann,
      computed: asMonth
        ? scaleAnnualComputedToMonth(ann.computed)
        : ann.computed,
    };
  }

  let left: Panel;
  let right: Panel;
  let byLine = aggregateRows(
    grain === "year"
      ? filterFactsYearActual(rows, line, entity, periodA)
      : filterFactsMonth(rows, line, entity, periodA),
    grain === "year" ? "year" : "month"
  ).byLine;

  if (mode === "aa") {
    const a = buildActual(periodA);
    const b = buildActual(periodB);
    left = {
      title: `実績 ${periodA}`,
      computed: a.computed,
      cashIn: a.cashIn,
      cashOut: a.cashOut,
      cashEnd: a.cashEnd,
      depreciation: a.depreciation,
      emptyHint: "この条件の実績がありません。下の月次フォームで保存してください。",
      fNote:
        grain === "month" && a.computed
          ? `F内訳: 月額 ${fmtYen(Math.round(a.fMonthlyPart))} + 年額÷12 ${fmtYen(Math.round(a.fAnnualAllocated))}`
          : undefined,
    };
    right = {
      title: `実績 ${periodB}`,
      computed: b.computed,
      cashIn: b.cashIn,
      cashOut: b.cashOut,
      cashEnd: b.cashEnd,
      depreciation: b.depreciation,
      emptyHint: "比較用のもう一方の実績がありません。",
    };
  } else if (mode === "ap") {
    const a = buildActual(periodA);
    const p = buildPlan(planYear, variantA, grain === "month");
    left = {
      title: `実績 ${periodA}`,
      computed: a.computed,
      cashIn: a.cashIn,
      cashOut: a.cashOut,
      cashEnd: a.cashEnd,
      depreciation: a.depreciation,
      emptyHint: "実績がありません。",
    };
    right = {
      title: `計画「${variantA}」${planYear}${grain === "month" ? "（÷12）" : ""}`,
      computed: p.computed,
      emptyHint: "この計画がありません。下の年次計画フォームで保存してください。",
    };
  } else {
    const p1 = buildPlan(planYear, variantA, grain === "month");
    const p2 = buildPlan(planYear, variantB, grain === "month");
    left = {
      title: `計画「${variantA}」${planYear}${grain === "month" ? "（÷12）" : ""}`,
      computed: p1.computed,
      emptyHint: "計画Aがありません。",
    };
    right = {
      title: `計画「${variantB}」${planYear}${grain === "month" ? "（÷12）" : ""}`,
      computed: p2.computed,
      emptyHint: "計画Bがありません。別パターン名で保存してください。",
    };
    byLine = [];
  }

  function href(next: Record<string, string>) {
    const p = new URLSearchParams({
      line,
      entity,
      grain,
      mode,
      a: periodA,
      b: periodB,
      py: planYear,
      va: variantA,
      vb: variantB,
      ...next,
    });
    return `/mq?${p.toString()}`;
  }

  const formMonth = grain === "month" ? periodA : defaultMonth;

  const bsAsOf =
    grain === "year" ? yearEndDate(periodA) : monthEndDate(periodA);
  const bsLine =
    line === "ai" ? "ai" : line === "realestate" ? "realestate" : "realestate";
  const requireInventory = line === "ai";

  let bsFields = null as ReturnType<typeof normalizeBs> | null;
  let bsCombineNote: string | null = null;
  let bsFormEntity: "personal" | "corporate" =
    entity === "corporate" ? "corporate" : "personal";
  let bsInitial: Partial<ReturnType<typeof normalizeBs>> & {
    note?: string | null;
  } = {};

  if (line === "all") {
    bsCombineNote =
      "事業線「全体」のB/Sは未対応です。不動産またはAIを選んで入力してください。";
  } else if (entity === "combined") {
    const pers = pickNearestBs(bsRows, bsLine, "personal", bsAsOf);
    const corp = pickNearestBs(bsRows, bsLine, "corporate", bsAsOf);
    if (!pers && !corp) {
      bsCombineNote = "個人・法人ともスナップがありません。片方ずつ穴埋めしてください。";
    } else if (!pers || !corp) {
      bsCombineNote =
        "合算には個人・法人の両方のスナップが必要です（いまは片方のみ表示）。";
      const one = pers || corp!;
      bsFields = normalizeBs(one);
      bsFormEntity = one.entity === "corporate" ? "corporate" : "personal";
      bsInitial = { ...bsFields, note: one.note };
    } else {
      bsFields = combineBs(normalizeBs(pers), normalizeBs(corp));
      bsFormEntity = "personal";
      bsInitial = { ...normalizeBs(pers), note: pers.note };
      bsCombineNote =
        "合算表示。穴埋めは主体を選んで個別保存（片側の欠損は合算でも要確認）。";
    }
  } else {
    const hit = pickNearestBs(bsRows, bsLine, entity, bsAsOf);
    if (hit) {
      bsFields = normalizeBs(hit);
      bsFormEntity = entity;
      bsInitial = { ...bsFields, note: hit.note };
      if (String(hit.as_of_date).slice(0, 10) !== bsAsOf) {
        bsCombineNote = `直近スナップ ${String(hit.as_of_date).slice(0, 10)} を表示（基準 ${bsAsOf}）`;
      }
    } else {
      bsFormEntity = entity;
      bsCombineNote = "この条件のB/Sスナップがありません。下の穴埋めで作成できます。";
    }
  }

  return (
    <Shell active="/mq" email={user?.email ?? null}>
      <p className="page-kicker">③ 事業 · MQ</p>
      <h1>MQ会計評価</h1>
      <p className="sub">
        実績は月次でチューニング、計画は年次で立てる。年額Fは月次で÷12。計画との差も同じMQ表で見る。
      </p>

      {error ? (
        <div className="card" style={{ marginTop: 12, borderColor: "var(--high)" }}>
          <p className="meta">読取エラー: {error.message}</p>
        </div>
      ) : null}

      <div className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">スライサー</span>
          <strong>集計条件</strong>
        </header>
        <div className="mq-slicer" style={{ marginTop: 10 }}>
          <div className="mq-slicer-group">
            <span className="meta">比較</span>
            {(
              [
                ["aa", "実績 ↔ 実績"],
                ["ap", "実績 ↔ 計画"],
                ["pp", "計画 ↔ 計画"],
              ] as const
            ).map(([v, lab]) => (
              <a
                key={v}
                className={`btn${mode === v ? " primary" : ""}`}
                href={href({ mode: v })}
              >
                {lab}
              </a>
            ))}
          </div>
          <div className="mq-slicer-group">
            <span className="meta">事業線</span>
            {(
              [
                ["realestate", "不動産"],
                ["ai", "AI"],
                ["all", "全体"],
              ] as const
            ).map(([v, lab]) => (
              <a
                key={v}
                className={`btn${line === v ? " primary" : ""}`}
                href={href({ line: v })}
              >
                {lab}
              </a>
            ))}
          </div>
          <div className="mq-slicer-group">
            <span className="meta">主体</span>
            {(
              [
                ["personal", "個人"],
                ["corporate", "法人"],
                ["combined", "合算"],
              ] as const
            ).map(([v, lab]) => (
              <a
                key={v}
                className={`btn${entity === v ? " primary" : ""}`}
                href={href({ entity: v })}
              >
                {lab}
              </a>
            ))}
          </div>
          <div className="mq-slicer-group">
            <span className="meta">粒度</span>
            <a
              className={`btn${grain === "month" ? " primary" : ""}`}
              href={href({
                grain: "month",
                a: defaultMonth,
                b: months[1] || defaultMonth,
              })}
            >
              月次
            </a>
            <a
              className={`btn${grain === "year" ? " primary" : ""}`}
              href={href({
                grain: "year",
                a: defaultYear,
                b: years[1] || defaultYear,
              })}
            >
              年次
            </a>
          </div>

          {mode !== "pp" ? (
            <div className="mq-slicer-group">
              <span className="meta">{mode === "ap" ? "実績の期間" : "左（実績）"}</span>
              <PeriodLinks
                grain={grain}
                months={months}
                years={years}
                current={periodA}
                makeHref={(v) => href({ a: v })}
              />
            </div>
          ) : null}
          {mode === "aa" ? (
            <div className="mq-slicer-group">
              <span className="meta">右（実績）</span>
              <PeriodLinks
                grain={grain}
                months={months}
                years={years}
                current={periodB}
                makeHref={(v) => href({ b: v })}
              />
            </div>
          ) : null}

          {mode !== "aa" ? (
            <>
              <div className="mq-slicer-group">
                <span className="meta">計画の年度</span>
                {(years.length ? years : [defaultYear]).slice(0, 12).map((y) => (
                  <a
                    key={y}
                    className={`btn${planYear === y ? " primary" : ""}`}
                    href={href({ py: y })}
                  >
                    {y}
                  </a>
                ))}
              </div>
              <div className="mq-slicer-group">
                <span className="meta">{mode === "pp" ? "計画A" : "計画"}</span>
                {(variants.length ? variants : [defaultVariant]).map((v) => (
                  <a
                    key={v}
                    className={`btn${variantA === v ? " primary" : ""}`}
                    href={href({ va: v })}
                  >
                    {v}
                  </a>
                ))}
              </div>
            </>
          ) : null}
          {mode === "pp" ? (
            <div className="mq-slicer-group">
              <span className="meta">計画B</span>
              {(variants.length ? variants : [defaultVariant]).map((v) => (
                <a
                  key={`b-${v}`}
                  className={`btn${variantB === v ? " primary" : ""}`}
                  href={href({ vb: v })}
                >
                  {v}
                </a>
              ))}
            </div>
          ) : null}
        </div>
        <p className="meta" style={{ marginTop: 8 }}>
          {lineLabel(line)} · {entityLabel(entity)} ·{" "}
          {grain === "month" ? "月次表示" : "年次表示"}
          {mode === "ap" && grain === "month"
            ? " · 計画側は年額÷12で月次換算"
            : ""}
          {entity === "combined" ? " · 合算は内部取引除外推奨" : ""}
        </p>
      </div>

      <div className="mq-dual" style={{ marginTop: 12 }}>
        <MqStrackPanel
          title={left.title}
          computed={left.computed}
          cashIn={left.cashIn}
          cashOut={left.cashOut}
          cashEnd={left.cashEnd}
          depreciation={left.depreciation}
          emptyHint={left.emptyHint}
        />
        <MqStrackPanel
          title={right.title}
          computed={right.computed}
          cashIn={right.cashIn}
          cashOut={right.cashOut}
          cashEnd={right.cashEnd}
          depreciation={right.depreciation}
          emptyHint={right.emptyHint}
        />
      </div>

      {left.fNote ? (
        <p className="meta" style={{ marginTop: 8 }}>
          {left.fNote}
        </p>
      ) : null}

      {line === "all" && byLine.length > 0 ? (
        <div className="card" style={{ marginTop: 12 }}>
          <header>
            <span className="lvl">内訳</span>
            <strong>左 · 不動産 / AI</strong>
          </header>
          <table style={{ marginTop: 8 }}>
            <thead>
              <tr>
                <th>事業線</th>
                <th className="num">MQ</th>
                <th className="num">F</th>
                <th className="num">G</th>
              </tr>
            </thead>
            <tbody>
              {byLine.map((b) => (
                <tr key={b.line}>
                  <td>{lineLabel(b.line)}</td>
                  <td className="num">{fmtYen(Math.round(b.computed.mq))}</td>
                  <td className="num">{fmtYen(Math.round(b.computed.f))}</td>
                  <td className="num">{fmtYen(Math.round(b.computed.g))}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      <div style={{ marginTop: 12 }}>
        <MqCompareBars
          titleA={left.title}
          titleB={right.title}
          rowsA={metricBars(left.computed)}
          rowsB={metricBars(right.computed)}
        />
      </div>

      <div style={{ marginTop: 16 }}>
        <MqBsPanel
          title={`${lineLabel(line)} · ${entityLabel(entity)}`}
          fields={bsFields}
          mqG={left.computed?.g ?? null}
          asOfLabel={bsAsOf}
          combineNote={bsCombineNote}
          requireInventory={requireInventory}
          defaultLine={bsLine}
          defaultEntity={bsFormEntity}
          defaultAsOf={bsAsOf}
          initial={bsInitial}
        />
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <header>
          <span className="lvl">Zaim取込</span>
          <strong>月次実績の自動集計（Phase C）</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          承認済み科目マップで事業系だけ集計します。手入力月は既定で保護。未分類は下に出し、MQからは除外（暫定）します。
        </p>
        <div style={{ marginTop: 10 }}>
          <MqZaimIngestPanel defaultYear={planYear} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <header>
          <span className="lvl">実績入力</span>
          <strong>月次オンゴーイング</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          空室は主に Q（稼働戸月）の減少。年払いは F年額。ローン元本は出金合計（Gに入れない）。
        </p>
        <div style={{ marginTop: 10 }}>
          <MqFactsForm
            defaultLine={line === "ai" ? "ai" : "realestate"}
            defaultEntity={entity === "corporate" ? "corporate" : "personal"}
            defaultMonth={formMonth.slice(0, 7)}
          />
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <header>
          <span className="lvl">計画入力</span>
          <strong>年次パターン</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          同じ年度に「基本」「家賃+5%」など複数パターンを保存し、上の比較で差し引きできます。数値は年額。
        </p>
        <div style={{ marginTop: 10 }}>
          <MqPlanForm
            defaultLine={line === "ai" ? "ai" : "realestate"}
            defaultEntity={entity === "corporate" ? "corporate" : "personal"}
            defaultYear={planYear}
            existingVariants={variants.length ? variants : ["基本", "家賃+5%", "空室改善"]}
          />
        </div>
      </div>

      <p className="meta" style={{ marginTop: 16 }}>
        買い進め（
        <a href="/realestate/buy-plan">/realestate/buy-plan</a>
        ）は物件条件。こちらは固定費込みの粗利評価です。
      </p>
    </Shell>
  );
}

function PeriodLinks({
  grain,
  months,
  years,
  current,
  makeHref,
}: {
  grain: GrainFilter;
  months: string[];
  years: string[];
  current: string;
  makeHref: (v: string) => string;
}) {
  const opts = grain === "year" ? years : months;
  if (opts.length === 0) {
    return <span className="meta">（保存後に選択可）</span>;
  }
  return (
    <>
      {opts.slice(0, 18).map((v) => (
        <a
          key={v}
          className={`btn${current === v ? " primary" : ""}`}
          href={makeHref(v)}
        >
          {v}
        </a>
      ))}
    </>
  );
}
