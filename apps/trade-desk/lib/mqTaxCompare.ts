/**
 * MQ会計 × 確定申告 — 比較物差し（申告を正にしない）。
 * 個人＝暦年、法人＝5月期。MQの万円と申告の円を揃えて差を出す。
 */

import type { MqComputed } from "@/lib/mqEquations";
import type { EntityFilter, LineFilter } from "@/lib/mqAggregate";
import {
  yearLabel,
  yen,
  zaimVsFiled,
  type TaxScope,
  type TaxYearMetricRow,
} from "@/lib/taxInsights";
import { yenToMan } from "@/lib/mqUnits";

export type MqTaxCompareRow = {
  id: string;
  label: string;
  mqMan: number | null;
  filedMan: number | null;
  diffMan: number | null;
  /** 差の典型理由（減価償却・元本・未取込など） */
  hint?: string;
  emphasize?: boolean;
};

export type MqTaxCompare = {
  scope: TaxScope;
  fiscalYear: number;
  yearLabel: string;
  line: LineFilter;
  entity: EntityFilter;
  hasMetrics: boolean;
  filingStatus: string | null;
  filedOn: string | null;
  rows: MqTaxCompareRow[];
  insights: string[];
  disclaimer: string;
};

/** 合算表示時 — 個人・法人を二段で比較（税務年度は主体ごと） */
export type MqTaxCompareDual = {
  fiscalYear: number;
  line: LineFilter;
  entity: "combined";
  personal: MqTaxCompare | null;
  corporate: MqTaxCompare | null;
  disclaimer: string;
};

const DISCLAIMER =
  "MQ実績は現金ベースの事業評価。確定申告は経費コントロール後の税務所得。申告をMQの正にはしません。";

function diffMan(
  mq: number | null,
  filed: number | null
): number | null {
  if (mq == null || filed == null) return null;
  return mq - filed;
}

function row(
  id: string,
  label: string,
  mqMan: number | null,
  filedYen: number | null,
  hint?: string,
  emphasize = false
): MqTaxCompareRow {
  const filedMan = filedYen != null ? yenToMan(filedYen) : null;
  return {
    id,
    label,
    mqMan,
    filedMan,
    diffMan: diffMan(mqMan, filedMan),
    hint,
    emphasize,
  };
}

export function taxScopeForMq(
  line: LineFilter,
  entity: EntityFilter
): TaxScope | null {
  if (entity === "combined" || line === "all") return null;
  if (entity === "corporate") return "corporate";
  if (entity === "personal") return "personal";
  return null;
}

function filedReIncome(m: TaxYearMetricRow | undefined): number | null {
  if (!m?.payload) return null;
  return yen(m.payload.re_income_jpy);
}

function filedReRevenue(m: TaxYearMetricRow | undefined): number | null {
  if (!m?.payload) return null;
  return yen(m.payload.re_revenue_jpy);
}

function filedReStatement(m: TaxYearMetricRow | undefined): number | null {
  if (!m?.payload) return null;
  return yen(m.payload.re_income_statement_jpy);
}

export function buildMqTaxCompare(args: {
  line: LineFilter;
  entity: EntityFilter;
  fiscalYear: number;
  computed: MqComputed | null;
  depreciationMan: number | null;
  metric: TaxYearMetricRow | undefined;
}): MqTaxCompare | null {
  const scope = taxScopeForMq(args.line, args.entity);
  if (!scope) return null;

  const c = args.computed;
  const m = args.metric;
  const rows: MqTaxCompareRow[] = [];

  if (args.line === "realestate" && scope === "personal") {
    rows.push(
      row(
        "pq",
        "売上（PQ）",
        c?.pq ?? null,
        filedReRevenue(m),
        "入金漏れ・敷金・期ズレ"
      ),
      row(
        "g",
        "利益（G）",
        c?.g ?? null,
        filedReIncome(m),
        "減価償却・利息・元本・経費寄せ",
        true
      )
    );
    const stmt = filedReStatement(m);
    if (stmt != null) {
      rows.push(
        row(
          "stmt",
          "収支内訳・所得",
          c?.g ?? null,
          stmt,
          "第一表③との差（土地利子制限等）"
        )
      );
    }
    rows.push(
      row(
        "depreciation",
        "減価償却",
        args.depreciationMan,
        null,
        "申告は収支内訳の行（科目別は未取込）"
      ),
      row(
        "income_tax",
        "所得税（参考）",
        null,
        yen(m?.income_tax_jpy),
        "MQには含めない"
      )
    );
  } else if (args.line === "realestate" && scope === "corporate") {
    rows.push(
      row(
        "pq",
        "売上（PQ）",
        c?.pq ?? null,
        yen(m?.revenue_jpy),
        "法人全体の売上（不動産単独ではない）"
      ),
      row(
        "g",
        "利益（G）",
        c?.g ?? null,
        yen(m?.ordinary_income_jpy),
        "法人全体の経常利益",
        true
      ),
      row(
        "depreciation",
        "減価償却",
        args.depreciationMan,
        null,
        "決算書の科目別は /tax で確認"
      ),
      row(
        "tax_payable",
        "納付税額（参考）",
        null,
        yen(m?.tax_payable_jpy) ?? yen(m?.corporate_tax_jpy),
        "MQには含めない"
      )
    );
  } else if (args.line === "ai") {
    rows.push(
      row(
        "pq",
        "売上（PQ）",
        c?.pq ?? null,
        scope === "corporate" ? yen(m?.revenue_jpy) : null,
        scope === "personal" ? "個人AIは申告KPI未整備" : undefined
      ),
      row(
        "g",
        "利益（G）",
        c?.g ?? null,
        scope === "corporate" ? yen(m?.ordinary_income_jpy) : null,
        "法人全体とAI単体は一致しない",
        true
      )
    );
  } else {
    return null;
  }

  const insights = buildInsights({
    scope,
    line: args.line,
    rows,
    hasMetrics: !!m,
    fiscalYear: args.fiscalYear,
  });

  return {
    scope,
    fiscalYear: args.fiscalYear,
    yearLabel: yearLabel(scope, args.fiscalYear),
    line: args.line,
    entity: args.entity,
    hasMetrics: !!m,
    filingStatus: m?.filing_status ?? null,
    filedOn: m?.filed_on ?? null,
    rows,
    insights,
    disclaimer: DISCLAIMER,
  };
}

function buildInsights(args: {
  scope: TaxScope;
  line: LineFilter;
  rows: MqTaxCompareRow[];
  hasMetrics: boolean;
  fiscalYear: number;
}): string[] {
  const out: string[] = [];
  if (!args.hasMetrics) {
    out.push(
      `${args.fiscalYear}年分の申告KPIが未登録です。/tax で登録すると比較できます。`
    );
    return out.slice(0, 3);
  }

  const gRow = args.rows.find((r) => r.id === "g");
  if (gRow?.mqMan != null && gRow.filedMan != null) {
    const vs = zaimVsFiled(
      gRow.mqMan * 10_000,
      gRow.filedMan * 10_000
    );
    if (vs.pct != null && Math.abs(vs.pct) >= 0.2) {
      const dir = vs.diff != null && vs.diff > 0 ? "上振れ" : "下振れ";
      out.push(
        `Gが申告所得より${dir}（約${Math.round(Math.abs(vs.pct) * 100)}%）。減価償却・借入利息・元本返済の差を疑うとよいです。`
      );
    } else if (gRow.diffMan != null && Math.abs(gRow.diffMan) <= 5) {
      out.push("Gと申告所得はおおむね一致。大きなズレはなさそうです。");
    }
  }

  const dep = args.rows.find((r) => r.id === "depreciation");
  if (dep?.mqMan != null && dep.mqMan > 0 && dep.filedMan == null) {
    out.push(
      "MQに減価償却メモあり。申告側の科目別は未取込のため、収支内訳行の手入力で差分分析できます。"
    );
  }

  if (args.line === "realestate" && args.scope === "corporate") {
    out.push("法人行は決算全体です。不動産MQだけと1対1にはなりません。");
  }

  return out.slice(0, 3);
}

export function buildMqTaxCompareDual(args: {
  line: LineFilter;
  fiscalYear: number;
  personal: {
    computed: MqComputed | null;
    depreciationMan: number | null;
    metric: TaxYearMetricRow | undefined;
  };
  corporate: {
    computed: MqComputed | null;
    depreciationMan: number | null;
    metric: TaxYearMetricRow | undefined;
  };
}): MqTaxCompareDual | null {
  if (args.line === "all") return null;

  const personal = buildMqTaxCompare({
    line: args.line,
    entity: "personal",
    fiscalYear: args.fiscalYear,
    computed: args.personal.computed,
    depreciationMan: args.personal.depreciationMan,
    metric: args.personal.metric,
  });
  const corporate = buildMqTaxCompare({
    line: args.line,
    entity: "corporate",
    fiscalYear: args.fiscalYear,
    computed: args.corporate.computed,
    depreciationMan: args.corporate.depreciationMan,
    metric: args.corporate.metric,
  });

  if (!personal && !corporate) return null;

  return {
    fiscalYear: args.fiscalYear,
    line: args.line,
    entity: "combined",
    personal,
    corporate,
    disclaimer: DISCLAIMER,
  };
}
