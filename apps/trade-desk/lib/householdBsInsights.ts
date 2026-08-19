import type { HouseholdBsRow, HouseholdBsView } from "./householdBsCompose";

export type HouseholdBsCashStatus = "余裕あり" | "注意" | "要資金調達";

export type HouseholdBsSummary = {
  cashStatus: HouseholdBsCashStatus;
  cashTotalJpy: number;
  accountingNetFlowJpy: number;
  debtServiceJpy: number;
  cashExpenseJpy: number;
  cashNetFlowJpy: number;
  nextPropertyJpy: number;
  bridgeNeedJpy: number;
  deployableCashJpy: number;
  fundingGapJpy: number;
  fundingNote: string;
  netWorthJpy: number;
  netWorthDeltaJpy: number | null;
  pocketIncomeJpy: number;
  pocketIncomeRatio: number | null;
  coreAssetJpy: number;
  themeAssetJpy: number;
};

export type HouseholdBsTrendRow = {
  year: number;
  incomeJpy: number;
  expenseJpy: number;
  debtServiceJpy: number;
  cashExpenseJpy: number;
  cashflowJpy: number;
  cashflowAfterDebtJpy: number;
  assetJpy: number;
  liabilityJpy: number;
  netWorthJpy: number;
  cashJpy: number;
  source: string | null;
  snapshotAsOf: string | null;
};

function sumBand(
  rows: HouseholdBsRow[],
  band: string,
  opts?: { countsOnly?: boolean; quadrant?: HouseholdBsRow["quadrant"] }
): number {
  return rows.reduce((sum, row) => {
    if (row.band !== band) return sum;
    if (opts?.countsOnly && !row.countsTowardTotal) return sum;
    if (opts?.quadrant && row.quadrant !== opts.quadrant) return sum;
    return sum + (row.amountJpy ?? 0);
  }, 0);
}

function sumIncomeExcludingBand(rows: HouseholdBsRow[], excludeBand: string): number {
  return rows.reduce((sum, row) => {
    if (row.quadrant !== "income" || !row.countsTowardTotal) return sum;
    if (row.band === excludeBand) return sum;
    return sum + (row.amountJpy ?? 0);
  }, 0);
}

export function cashStatusFromSummary(
  fundingGapJpy: number,
  deployableCashJpy: number,
  netFlowJpy: number
): HouseholdBsCashStatus {
  if (fundingGapJpy > 0) return "要資金調達";
  if (deployableCashJpy <= 0 || netFlowJpy <= 0) return "注意";
  return "余裕あり";
}

export function buildHouseholdBsSummary(
  view: HouseholdBsView,
  prior?: HouseholdBsTrendRow | null
): HouseholdBsSummary {
  const cashTotalJpy = sumBand(view.rows, "cash", { countsOnly: true });
  const nextPropertyJpy = sumBand(view.rows, "next_property");
  const bridgeNeedJpy = sumBand(view.rows, "bridge", {
    countsOnly: true,
    quadrant: "liability",
  });
  const debtServiceJpy = sumBand(view.rows, "debt_service", {
    quadrant: "expense",
  });
  const coreAssetJpy = sumBand(view.rows, "sleep", { countsOnly: true });
  const themeAssetJpy = sumBand(view.rows, "theme", { countsOnly: true });
  const accountingNetFlowJpy = view.totals.incomeJpy - view.totals.expenseJpy;
  const cashExpenseJpy = view.totals.expenseJpy + debtServiceJpy;
  const cashNetFlowJpy = view.totals.incomeJpy - cashExpenseJpy;
  const deployableCashJpy = Math.max(cashTotalJpy - nextPropertyJpy - bridgeNeedJpy, 0);
  const fundingGapJpy = Math.max(bridgeNeedJpy - cashTotalJpy, 0);
  const fundingNote =
    fundingGapJpy > 0
      ? "寄せ・保険貸付・法人余力の確認が先"
      : deployableCashJpy > 0
        ? "防衛と次物件キープを差し引いても余力あり"
        : "現金はあるが、防衛・次物件・引落で使い切る状態";
  const pocketIncomeJpy = sumIncomeExcludingBand(view.rows, "engine");
  const pocketIncomeRatio =
    view.totals.incomeJpy > 0 ? pocketIncomeJpy / view.totals.incomeJpy : null;
  const netWorthJpy = view.totals.assetJpy - view.totals.liabilityJpy;

  return {
    cashStatus: cashStatusFromSummary(fundingGapJpy, deployableCashJpy, cashNetFlowJpy),
    cashTotalJpy,
    accountingNetFlowJpy,
    debtServiceJpy,
    cashExpenseJpy,
    cashNetFlowJpy,
    nextPropertyJpy,
    bridgeNeedJpy,
    deployableCashJpy,
    fundingGapJpy,
    fundingNote,
    netWorthJpy,
    netWorthDeltaJpy: prior ? netWorthJpy - prior.netWorthJpy : null,
    pocketIncomeJpy,
    pocketIncomeRatio,
    coreAssetJpy,
    themeAssetJpy,
  };
}

export function buildHouseholdBsTrendRow(view: HouseholdBsView): HouseholdBsTrendRow {
  const cashJpy = sumBand(view.rows, "cash", { countsOnly: true });
  const debtServiceJpy = sumBand(view.rows, "debt_service", {
    quadrant: "expense",
  });
  const cashExpenseJpy = view.totals.expenseJpy + debtServiceJpy;
  return {
    year: Number(view.year),
    incomeJpy: view.totals.incomeJpy,
    expenseJpy: view.totals.expenseJpy,
    debtServiceJpy,
    cashExpenseJpy,
    cashflowJpy: view.totals.incomeJpy - view.totals.expenseJpy,
    cashflowAfterDebtJpy: view.totals.incomeJpy - cashExpenseJpy,
    assetJpy: view.totals.assetJpy,
    liabilityJpy: view.totals.liabilityJpy,
    netWorthJpy: view.totals.assetJpy - view.totals.liabilityJpy,
    cashJpy,
    source: view.snapshotSource ?? null,
    snapshotAsOf: view.snapshotAsOf ?? null,
  };
}

export function sortTrendRows(rows: HouseholdBsTrendRow[]): HouseholdBsTrendRow[] {
  return [...rows].sort((a, b) => a.year - b.year);
}
