/**
 * 法人: Kneesbee/MyKomon の statement·plan を事業 BS·PL に重ねる。
 * Zaim 合成は残しつつ、主要行は税務正本を優先表示。
 * 合算ビューでは法人列だけ差し替え、PL合計は列合算で再計算（個人と二重にしない）。
 */
import { computeRatios, sumPlColumns } from "./reBusinessPlMath";
import {
  sourced,
  yenToMan,
  type ReBusinessPlModel,
  type RePlColumn,
} from "./reBusinessPlTypes";

export type ReStatementRow = {
  label?: string | null;
  source?: string | null;
  fiscal_year?: number | null;
  period_end?: string | null;
  revenue_jpy?: number | string | null;
  operating_profit_jpy?: number | string | null;
  pretax_profit_jpy?: number | string | null;
  tax_jpy?: number | string | null;
  net_income_jpy?: number | string | null;
  capital_jpy?: number | string | null;
  retained_earnings_jpy?: number | string | null;
  officer_loan_jpy?: number | string | null;
  bank_loan_jpy?: number | string | null;
  pl_json?: Record<string, unknown> | null;
  bs_json?: Record<string, unknown> | null;
  reconcile_notes?: string | null;
};

export type ReAnnualPlanRow = {
  fiscal_year: number;
  label?: string | null;
  revenue_jpy?: number | string | null;
  pretax_profit_jpy?: number | string | null;
  cash_flow_jpy?: number | string | null;
  occupancy_pct?: number | string | null;
};

export type ReGlAggRow = {
  account_name: string;
  cnt: number;
  net_jpy: number;
};

function n(v: number | string | null | undefined): number | null {
  if (v == null || v === "") return null;
  const x = Number(v);
  return Number.isFinite(x) ? x : null;
}

function overlayPlTotals(
  col: RePlColumn,
  st: ReStatementRow,
  planCf: number | null
): RePlColumn {
  const revenue = n(st.revenue_jpy);
  const pretax = n(st.pretax_profit_jpy);
  const tax = n(st.tax_jpy);
  const op = n(st.operating_profit_jpy);
  const pl = st.pl_json && typeof st.pl_json === "object" ? st.pl_json : {};
  const interest = n(pl.interest_jpy as number | string | null | undefined);
  const dep = n(pl.depreciation_jpy as number | string | null | undefined);
  const cf =
    planCf ?? n(pl.cash_flow_jpy as number | string | null | undefined);

  return {
    ...col,
    rentIncome: sourced(yenToMan(revenue), "statement", "Kneesbee/MyKomon"),
    interest: sourced(
      yenToMan(interest),
      interest != null ? "statement" : col.interest.source,
      "事業計画"
    ),
    depreciation: sourced(
      yenToMan(dep),
      dep != null ? "statement" : col.depreciation.source,
      "事業計画"
    ),
    pretaxProfit: sourced(yenToMan(pretax), "statement", "R8税引前＝不動産所得"),
    tax: sourced(yenToMan(tax), "statement", "法人税等"),
    afterTaxProfit: sourced(
      yenToMan(
        pretax != null && tax != null ? pretax - (pretax > 0 ? tax : 0) : pretax
      ),
      "statement"
    ),
    cashFlow: sourced(yenToMan(cf), "plan", "事業計画・手残り"),
    // 営業利益はメモ用に expense 側は触らない（行が無いため notes で示す）
    expenseOther:
      op != null
        ? {
            ...col.expenseOther,
            note: `参考・営業利益 ${(yenToMan(op) ?? 0).toFixed(0)}万円（R8メール）`,
          }
        : col.expenseOther,
  };
}

export function applyCorporateStatementOverlay(
  model: ReBusinessPlModel,
  args: {
    statement: ReStatementRow | null;
    plans: ReAnnualPlanRow[];
    glTop: ReGlAggRow[];
  }
): ReBusinessPlModel {
  const { statement, plans, glTop } = args;
  if (model.entity === "personal") {
    return {
      ...model,
      notes: [
        ...model.notes,
        "個人は Zaim＋収支内訳書簿価が正。法人の Kneesbee 正本は「法人」タブ。",
      ],
    };
  }
  if (!statement) {
    return {
      ...model,
      notes: [
        ...model.notes,
        "法人の kurashift_re_statements が未取込です。MyKomon 取込後に再読込してください。",
      ],
    };
  }

  const sameYearPlan = plans.find((p) => p.fiscal_year === model.year);
  const planCf = n(sameYearPlan?.cash_flow_jpy);
  const notes = [
    ...model.notes,
    `法人正本: ${statement.label || statement.source || "statement"}（Zaimより優先・期＝${model.year}年5月期末）`,
  ];
  if (statement.reconcile_notes) notes.push(statement.reconcile_notes);
  if (model.entity === "combined") {
    notes.push(
      "合算: 個人は Zaim＋収支内訳、法人は Kneesbee statement。家計BSへは二重計上しない。"
    );
  }

  const columns = model.columns.map((c) => {
    if (model.entity === "corporate" || c.entity === "corporate") {
      return overlayPlTotals(c, statement, planCf);
    }
    return c;
  });

  const totalPl =
    model.entity === "corporate"
      ? overlayPlTotals(model.totalPl, statement, planCf)
      : sumPlColumns(columns, "合計", model.taxRate);

  const capital = n(statement.capital_jpy);
  const retained = n(statement.retained_earnings_jpy);
  const officer = n(statement.officer_loan_jpy);
  const plj =
    statement.pl_json && typeof statement.pl_json === "object"
      ? statement.pl_json
      : {};
  const bsj =
    statement.bs_json && typeof statement.bs_json === "object"
      ? statement.bs_json
      : {};

  let totalBs = model.totalBs;
  let bsColumns = model.bsColumns;
  if (model.entity === "corporate") {
    totalBs = {
      ...model.totalBs,
      capital: sourced(yenToMan(capital), "statement"),
      retained: sourced(
        yenToMan(retained),
        "statement",
        "累積損益（Notion概算可）"
      ),
      equity: sourced(
        yenToMan(
          capital != null && retained != null ? capital + retained : null
        ),
        "statement",
        "簿価純資産（債務超過見え）"
      ),
    };
  } else if (model.entity === "combined") {
    bsColumns = model.bsColumns.map((c) => {
      if (c.entity !== "corporate") return c;
      return {
        ...c,
        capital: sourced(yenToMan(capital), "statement"),
        retained: sourced(yenToMan(retained), "statement"),
        equity: sourced(
          yenToMan(
            capital != null && retained != null ? capital + retained : null
          ),
          "statement"
        ),
      };
    });
    // 合算の合計BSは物件列合算のまま（資本は法人列にのみ statement）。二重計上しない。
    notes.push(
      "合算BS合計の資本は従来合成。法人列の資本・剰余は Kneesbee statement。"
    );
  }

  const ratios = computeRatios(totalBs, totalPl.cashFlow.man);

  return {
    ...model,
    columns,
    totalPl,
    bsColumns,
    totalBs,
    ratios,
    notes,
    corporateOverlay: {
      statementLabel: statement.label || statement.source || null,
      reconcileNotes: statement.reconcile_notes || null,
      plans: plans.map((p) => ({
        fiscalYear: p.fiscal_year,
        label: p.label ?? null,
        revenueMan: yenToMan(n(p.revenue_jpy)),
        pretaxMan: yenToMan(n(p.pretax_profit_jpy)),
        cashFlowMan: yenToMan(n(p.cash_flow_jpy)),
        occupancyPct: n(p.occupancy_pct),
      })),
      glAccountTop: glTop.map((g) => ({
        account: g.account_name,
        count: g.cnt,
        netMan: yenToMan(g.net_jpy),
      })),
      kpis: {
        fullRentMan: yenToMan(n(plj.full_rent_jpy as number | string | null)),
        bookDebtExcessMan: yenToMan(
          n(bsj.debt_excess_book_jpy as number | string | null)
        ),
        officerLoanMan: yenToMan(officer),
        substantiveEquityNote:
          typeof bsj.substantive_equity_note === "string"
            ? bsj.substantive_equity_note
            : null,
      },
    },
  };
}
