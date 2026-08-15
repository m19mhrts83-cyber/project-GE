import Shell from "@/components/Shell";
import MqCompareBars from "@/components/MqCompareBars";
import MqFactsForm from "@/components/MqFactsForm";
import MqStrackPanel from "@/components/MqStrackPanel";
import { fmtYen } from "@/lib/format";
import {
  aggregateRows,
  availableMonths,
  availableYears,
  entityLabel,
  filterFactsMonth,
  filterFactsYearActual,
  lineLabel,
  metricBars,
  type EntityFilter,
  type GrainFilter,
  type LineFilter,
  type MqFactRow,
} from "@/lib/mqAggregate";
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
  const monthsHint = availableMonths([]);
  void monthsHint;

  const { data: raw, error } = await supabase
    .from("kurashift_mq_period_facts")
    .select("*")
    .order("period_month", { ascending: false })
    .limit(500);

  const rows = (raw ?? []) as MqFactRow[];
  const months = availableMonths(rows);
  const years = availableYears(rows);
  const defaultMonth = months[0] || currentMonth();
  const defaultYear = years[0] || String(new Date().getFullYear());

  const periodA =
    grain === "year"
      ? one(sp, "a", defaultYear).slice(0, 4)
      : one(sp, "a", defaultMonth).slice(0, 7);
  const periodB =
    grain === "year"
      ? one(sp, "b", years[1] || defaultYear).slice(0, 4)
      : one(sp, "b", months[1] || defaultMonth).slice(0, 7);

  const rowsA =
    grain === "year"
      ? filterFactsYearActual(rows, line, entity, periodA)
      : filterFactsMonth(rows, line, entity, periodA);
  const rowsB =
    grain === "year"
      ? filterFactsYearActual(rows, line, entity, periodB)
      : filterFactsMonth(rows, line, entity, periodB);

  const aggA = aggregateRows(rowsA, grain === "year" ? "year" : "month");
  const aggB = aggregateRows(rowsB, grain === "year" ? "year" : "month");

  function href(next: Record<string, string>) {
    const p = new URLSearchParams({
      line,
      entity,
      grain,
      a: periodA,
      b: periodB,
      ...next,
    });
    return `/mq?${p.toString()}`;
  }

  const formMonth = grain === "month" ? periodA : defaultMonth;

  return (
    <Shell active="/mq" email={user?.email ?? null}>
      <p className="page-kicker">③ 事業 · MQ</p>
      <h1>MQ会計評価</h1>
      <p className="sub">
        直接原価で粗利（MQ）を見る。実績は月次でチューニング、計画は年次（Phase
        D）。年額固定費は月表示で÷12按分。
      </p>

      {error ? (
        <div className="card" style={{ marginTop: 12, borderColor: "var(--high)" }}>
          <p className="meta">
            読取エラー: {error.message}
            （テーブル未作成なら Jarvis に DDL 適用を依頼）
          </p>
        </div>
      ) : null}

      <div className="card" style={{ marginTop: 12 }}>
        <header>
          <span className="lvl">スライサー</span>
          <strong>集計条件</strong>
        </header>
        <div className="mq-slicer" style={{ marginTop: 10 }}>
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
              href={href({ grain: "month", a: defaultMonth, b: months[1] || defaultMonth })}
            >
              月次（実績チューニング）
            </a>
            <a
              className={`btn${grain === "year" ? " primary" : ""}`}
              href={href({
                grain: "year",
                a: defaultYear,
                b: years[1] || defaultYear,
              })}
            >
              年次（締めて評価）
            </a>
          </div>
          <div className="mq-slicer-group">
            <span className="meta">左の期間</span>
            <PeriodLinks
              grain={grain}
              months={months}
              years={years}
              current={periodA}
              makeHref={(v) => href({ a: v })}
            />
          </div>
          <div className="mq-slicer-group">
            <span className="meta">右の期間</span>
            <PeriodLinks
              grain={grain}
              months={months}
              years={years}
              current={periodB}
              makeHref={(v) => href({ b: v })}
            />
          </div>
        </div>
        <p className="meta" style={{ marginTop: 8 }}>
          表示中: {lineLabel(line)} · {entityLabel(entity)} ·{" "}
          {grain === "month" ? "月次" : "年次"}
          {entity === "combined"
            ? "（合算は内部取引を除いた値の入力を推奨）"
            : ""}
          {grain === "month"
            ? " · F年額は÷12で按分"
            : " · 年額Fは年に1回分だけ加算（月次行の重複なし）"}
        </p>
      </div>

      <div className="mq-dual" style={{ marginTop: 12 }}>
        <MqStrackPanel
          title={`左 ${periodA}`}
          computed={aggA.computed}
          cashIn={aggA.cashIn}
          cashOut={aggA.cashOut}
          cashEnd={aggA.cashEnd}
          depreciation={aggA.depreciation}
          emptyHint="この条件の実績がありません。下のフォームで月次を保存してください。"
        />
        <MqStrackPanel
          title={`右 ${periodB}`}
          computed={aggB.computed}
          cashIn={aggB.cashIn}
          cashOut={aggB.cashOut}
          cashEnd={aggB.cashEnd}
          depreciation={aggB.depreciation}
          emptyHint="比較用のもう一方の期間データがありません。"
        />
      </div>

      {line === "all" && aggA.byLine.length > 0 ? (
        <div className="card" style={{ marginTop: 12 }}>
          <header>
            <span className="lvl">内訳</span>
            <strong>左期間 · 不動産 / AI</strong>
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
              {aggA.byLine.map((b) => (
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

      {grain === "month" && aggA.computed ? (
        <p className="meta" style={{ marginTop: 8 }}>
          左の F 内訳目安: 月額分 {fmtYen(Math.round(aggA.fMonthlyPart))} + 年額按分{" "}
          {fmtYen(Math.round(aggA.fAnnualAllocated))}
        </p>
      ) : null}

      <div style={{ marginTop: 12 }}>
        <MqCompareBars
          titleA={`左 ${periodA}`}
          titleB={`右 ${periodB}`}
          rowsA={metricBars(aggA.computed)}
          rowsB={metricBars(aggB.computed)}
        />
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <header>
          <span className="lvl">軽量B/S</span>
          <strong>要確認（捏造しない）</strong>
        </header>
        <p className="meta" style={{ marginTop: 8 }}>
          流動・固定／他人資本・自己資本は、正本（借入トラッカー／税理士資料）が揃い次第ここに載せます。現時点は未入力です。
        </p>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <header>
          <span className="lvl">実績入力</span>
          <strong>月次オンゴーイング</strong>
        </header>
        <p className="meta" style={{ marginTop: 6 }}>
          空室は主に Q（稼働戸月）の減少として見ます。固都税など年払いは「F年額」へ。ローン元本は出金合計側（Gに入れない）。
        </p>
        <div style={{ marginTop: 10 }}>
          <MqFactsForm
            defaultLine={line === "ai" ? "ai" : "realestate"}
            defaultEntity={entity === "corporate" ? "corporate" : "personal"}
            defaultMonth={formMonth}
          />
        </div>
      </div>

      <p className="meta" style={{ marginTop: 16 }}>
        買い進めプラン（
        <a href="/realestate/buy-plan">/realestate/buy-plan</a>
        ）は物件条件の検討。こちらは固定費込みで粗利が残るかの評価です。次フェーズ:
        年次計画パターン比較（Phase D）。
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
