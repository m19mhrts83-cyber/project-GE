/**
 * ゼミExcel準拠の PL / CF / BS / 指標計算（純関数）
 */

import {
  DEFAULT_TAX_RATE,
  sourced,
  sumMan,
  type AmountSource,
  type ReBsColumn,
  type RePlColumn,
  type RePlRatios,
  type SourcedAmount,
} from "./reBusinessPlTypes";

export function expenseExDepFromParts(
  management: number | null,
  taxPublic: number | null,
  repair: number | null,
  other: number | null,
  source: AmountSource = "zaim"
): SourcedAmount {
  const man = sumMan([management, taxPublic, repair, other]);
  return sourced(man, man == null ? null : source);
}

export function depreciationTotal(
  building: number | null,
  equipment: number | null,
  source: AmountSource = "master"
): SourcedAmount {
  const man = sumMan([building, equipment]);
  return sourced(man, man == null ? null : source);
}

/** 税前 = 収入 − 経費 − 償却 − 利息 */
export function pretaxProfit(
  rent: number | null,
  expenseExDep: number | null,
  dep: number | null,
  interest: number | null
): SourcedAmount {
  if (
    rent == null &&
    expenseExDep == null &&
    dep == null &&
    interest == null
  ) {
    return sourced(null, null);
  }
  const v =
    (rent ?? 0) - (expenseExDep ?? 0) - (dep ?? 0) - (interest ?? 0);
  return sourced(v, "derived");
}

export function taxOnPretax(
  pretax: number | null,
  rate = DEFAULT_TAX_RATE
): SourcedAmount {
  if (pretax == null) return sourced(null, null);
  if (pretax <= 0) return sourced(0, "derived", `税率${rate}・赤字は0`);
  return sourced(Math.round(pretax * rate), "derived", `税率${rate}`);
}

export function afterTax(
  pretax: number | null,
  tax: number | null
): SourcedAmount {
  if (pretax == null && tax == null) return sourced(null, null);
  return sourced((pretax ?? 0) - (tax ?? 0), "derived");
}

/**
 * CF = 税後 + 減価償却 + 税金 − 税金支払 − 元金返済
 * （Excel: SUM(税後,償却戻し,税金戻し) − SUM(税金支払,元金)）
 */
export function cashFlowBridge(args: {
  afterTax: number | null;
  depreciation: number | null;
  tax: number | null;
  taxPaid: number | null;
  principal: number | null;
}): SourcedAmount {
  const {
    afterTax: at,
    depreciation: dep,
    tax,
    taxPaid,
    principal,
  } = args;
  if (
    at == null &&
    dep == null &&
    tax == null &&
    taxPaid == null &&
    principal == null
  ) {
    return sourced(null, null);
  }
  const v =
    (at ?? 0) +
    (dep ?? 0) +
    (tax ?? 0) -
    (taxPaid ?? 0) -
    (principal ?? 0);
  return sourced(v, "derived");
}

export function currentAssets(
  cash: number | null,
  receivables: number | null
): SourcedAmount {
  const man = sumMan([cash, receivables]);
  return sourced(man, man == null ? null : "derived");
}

export function fixedAssetsSum(
  building: number | null,
  equipment: number | null,
  land: number | null,
  investments: number | null
): SourcedAmount {
  const man = sumMan([building, equipment, land, investments]);
  return sourced(man, man == null ? null : "derived");
}

export function totalAssets(
  current: number | null,
  fixed: number | null
): SourcedAmount {
  const man = sumMan([current, fixed]);
  return sourced(man, man == null ? null : "derived");
}

export function currentLiab(
  stLoan: number | null,
  payables: number | null
): SourcedAmount {
  const man = sumMan([stLoan, payables]);
  return sourced(man, man == null ? null : "derived");
}

export function fixedLiab(
  ltLoan: number | null,
  deposits: number | null
): SourcedAmount {
  const man = sumMan([ltLoan, deposits]);
  return sourced(man, man == null ? null : "derived");
}

export function totalLiab(
  current: number | null,
  fixed: number | null
): SourcedAmount {
  const man = sumMan([current, fixed]);
  return sourced(man, man == null ? null : "derived");
}

/**
 * 資本側をバランスさせる簡易法。
 * capital / retained が両方 null のとき、資産−負債を retained に載せる（推定）。
 */
export function balanceEquity(args: {
  totalAssets: number | null;
  totalLiab: number | null;
  capital: number | null;
  retained: number | null;
}): {
  capital: SourcedAmount;
  retained: SourcedAmount;
  equity: SourcedAmount;
  totalLiabEquity: SourcedAmount;
  balanced: boolean;
} {
  const { totalAssets: ta, totalLiab: tl } = args;
  let capital = args.capital;
  let retained = args.retained;
  let estimated = false;

  if (ta != null && tl != null && capital == null && retained == null) {
    retained = ta - tl;
    estimated = true;
  }

  const equityMan = sumMan([capital, retained]);
  const totalLe = sumMan([tl, equityMan]);
  const balanced =
    ta != null &&
    totalLe != null &&
    Math.abs(ta - totalLe) <= 1;

  return {
    capital: sourced(
      capital,
      capital == null ? null : estimated ? "estimated" : "override"
    ),
    retained: sourced(
      retained,
      retained == null ? null : estimated ? "estimated" : "override",
      estimated ? "資産−負債（推定）" : undefined
    ),
    equity: sourced(equityMan, equityMan == null ? null : "derived"),
    totalLiabEquity: sourced(totalLe, totalLe == null ? null : "derived"),
    balanced,
  };
}

/** 自己資本比率 = 純資産 / 資産合計 */
export function equityRatio(
  equity: number | null,
  assets: number | null
): number | null {
  if (equity == null || assets == null || assets <= 0) return null;
  return equity / assets;
}

/** 流動比率 = 流動資産 / 流動負債 */
export function currentRatio(
  ca: number | null,
  cl: number | null
): number | null {
  if (ca == null || cl == null || cl <= 0) return null;
  return ca / cl;
}

/** 債務償還年数 = 固定負債 / 年CF（Excel: 固定負債/CF） */
export function debtPaybackYears(
  fixedLiabilities: number | null,
  cf: number | null
): number | null {
  if (fixedLiabilities == null || cf == null || cf <= 0) return null;
  return fixedLiabilities / cf;
}

/** ROI = 年CF / 資本（Excel: CF/資本金側） */
export function roiOnEquity(
  cf: number | null,
  equity: number | null
): number | null {
  if (cf == null || equity == null || equity <= 0) return null;
  return cf / equity;
}

export function computeRatios(
  bs: Pick<
    ReBsColumn,
    "totalAssets" | "equity" | "currentAssets" | "currentLiab" | "fixedLiab"
  >,
  cf: number | null
): RePlRatios {
  return {
    equityRatio: equityRatio(bs.equity.man, bs.totalAssets.man),
    currentRatio: currentRatio(bs.currentAssets.man, bs.currentLiab.man),
    debtPaybackYears: debtPaybackYears(bs.fixedLiab.man, cf),
    roi: roiOnEquity(cf, bs.equity.man),
  };
}

/** 定額償却（年）= 取得簿価 / 耐用年数。経過年で残存は別途 */
export function straightLineDepMan(
  bookYen: number | null | undefined,
  years: number | null | undefined
): number | null {
  if (bookYen == null || years == null || years <= 0) return null;
  return Math.round(bookYen / years / 10_000);
}

/**
 * 期末簿価（万円）= max(0, 取得 − 年償却 × 経過年)
 * elapsedYears は取得日から対象年末までの経過（端数切り捨て）
 */
export function netBookMan(
  bookYen: number | null | undefined,
  years: number | null | undefined,
  elapsedYears: number
): number | null {
  if (bookYen == null) return null;
  const depYear = straightLineDepMan(bookYen, years);
  if (depYear == null || years == null) return Math.round(bookYen / 10_000);
  const elapsed = Math.max(0, Math.min(elapsedYears, years));
  return Math.max(0, Math.round(bookYen / 10_000) - depYear * elapsed);
}

export function yearsElapsed(acquired: string, asOfYear: number): number {
  const m = acquired.match(/^(\d{4})/);
  if (!m) return 0;
  const y = Number(m[1]);
  return Math.max(0, asOfYear - y);
}

export function emptyPlColumn(
  propertyId: string,
  label: string,
  entity: "personal" | "corporate" | null
): RePlColumn {
  const z = sourced(null, null);
  return {
    propertyId,
    label,
    entity,
    rentIncome: z,
    expenseManagement: z,
    expenseTaxPublic: z,
    expenseRepair: z,
    expenseOther: z,
    expenseExDep: z,
    depreciationBuilding: z,
    depreciationEquipment: z,
    depreciation: z,
    interest: z,
    pretaxProfit: z,
    tax: z,
    afterTaxProfit: z,
    taxPaid: z,
    principalRepay: z,
    cashFlow: z,
  };
}

export function finalizePlColumn(col: RePlColumn, taxRate: number): RePlColumn {
  const expenseExDep = expenseExDepFromParts(
    col.expenseManagement.man,
    col.expenseTaxPublic.man,
    col.expenseRepair.man,
    col.expenseOther.man,
    col.expenseManagement.source || "zaim"
  );
  const depreciation = depreciationTotal(
    col.depreciationBuilding.man,
    col.depreciationEquipment.man,
    "master"
  );
  const pretax = pretaxProfit(
    col.rentIncome.man,
    expenseExDep.man,
    depreciation.man,
    col.interest.man
  );
  const tax = taxOnPretax(pretax.man, taxRate);
  const after = afterTax(pretax.man, tax.man);
  const taxPaid = col.taxPaid.man != null ? col.taxPaid : sourced(0, "estimated", "初回は0");
  const cf = cashFlowBridge({
    afterTax: after.man,
    depreciation: depreciation.man,
    tax: tax.man,
    taxPaid: taxPaid.man,
    principal: col.principalRepay.man,
  });
  return {
    ...col,
    expenseExDep,
    depreciation,
    pretaxProfit: pretax,
    tax,
    afterTaxProfit: after,
    taxPaid,
    cashFlow: cf,
  };
}

export function sumPlColumns(
  cols: RePlColumn[],
  label = "合計",
  taxRate = DEFAULT_TAX_RATE
): RePlColumn {
  const pick = (fn: (c: RePlColumn) => SourcedAmount): SourcedAmount => {
    const mans = cols.map((c) => fn(c).man);
    const man = sumMan(mans);
    return sourced(man, man == null ? null : "derived");
  };
  const base = emptyPlColumn("_total", label, null);
  return finalizePlColumn(
    {
      ...base,
      rentIncome: pick((c) => c.rentIncome),
      expenseManagement: pick((c) => c.expenseManagement),
      expenseTaxPublic: pick((c) => c.expenseTaxPublic),
      expenseRepair: pick((c) => c.expenseRepair),
      expenseOther: pick((c) => c.expenseOther),
      depreciationBuilding: pick((c) => c.depreciationBuilding),
      depreciationEquipment: pick((c) => c.depreciationEquipment),
      interest: pick((c) => c.interest),
      principalRepay: pick((c) => c.principalRepay),
      taxPaid: pick((c) => c.taxPaid),
    },
    taxRate
  );
}
