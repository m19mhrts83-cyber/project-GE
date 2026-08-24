/**
 * 不動産事業 BS・PL（ファイナンス戦略ゼミ Excel 準拠）
 * 単位: 万円（表示）。内部計算の入力は円でも可。
 */

export type RePlEntity = "personal" | "corporate" | "combined";

export type AmountSource =
  | "zaim"
  | "loan_tracker"
  | "master"
  | "mq_bs"
  | "override"
  | "estimated"
  | "derived"
  | "tax_return";

export type SourcedAmount = {
  man: number | null;
  source: AmountSource | null;
  note?: string;
};

/** PL 1物件（または合算）列 */
export type RePlColumn = {
  propertyId: string;
  label: string;
  entity: "personal" | "corporate" | null;
  /** 不動産収入 */
  rentIncome: SourcedAmount;
  /** 経費内訳（減価償却除く） */
  expenseManagement: SourcedAmount;
  expenseTaxPublic: SourcedAmount;
  expenseRepair: SourcedAmount;
  expenseOther: SourcedAmount;
  /** 経費合計（減価償却除く） */
  expenseExDep: SourcedAmount;
  depreciationBuilding: SourcedAmount;
  depreciationEquipment: SourcedAmount;
  depreciation: SourcedAmount;
  interest: SourcedAmount;
  pretaxProfit: SourcedAmount;
  tax: SourcedAmount;
  afterTaxProfit: SourcedAmount;
  /** CF 橋渡し */
  taxPaid: SourcedAmount;
  principalRepay: SourcedAmount;
  cashFlow: SourcedAmount;
};

export type ReBsColumn = {
  propertyId: string;
  label: string;
  entity: "personal" | "corporate" | null;
  cash: SourcedAmount;
  receivables: SourcedAmount;
  currentAssets: SourcedAmount;
  building: SourcedAmount;
  equipment: SourcedAmount;
  land: SourcedAmount;
  investments: SourcedAmount;
  fixedAssets: SourcedAmount;
  totalAssets: SourcedAmount;
  stLoan: SourcedAmount;
  payables: SourcedAmount;
  currentLiab: SourcedAmount;
  ltLoan: SourcedAmount;
  deposits: SourcedAmount;
  fixedLiab: SourcedAmount;
  totalLiab: SourcedAmount;
  capital: SourcedAmount;
  retained: SourcedAmount;
  equity: SourcedAmount;
  totalLiabEquity: SourcedAmount;
  /** 負債・純資産が資産と一致するか（推定資本込み） */
  balanced: boolean;
};

export type RePlRatios = {
  equityRatio: number | null;
  currentRatio: number | null;
  debtPaybackYears: number | null;
  roi: number | null;
};

export type ReBusinessPlModel = {
  year: number;
  entity: RePlEntity;
  taxRate: number;
  columns: RePlColumn[];
  totalPl: RePlColumn;
  bsColumns: ReBsColumn[];
  totalBs: ReBsColumn;
  ratios: RePlRatios;
  notes: string[];
};

export const DEFAULT_TAX_RATE = 0.2;

export function yenToMan(yen: number | null | undefined): number | null {
  if (yen == null || !Number.isFinite(Number(yen))) return null;
  return Math.round(Number(yen) / 10_000);
}

export function sumMan(
  parts: (number | null | undefined)[]
): number | null {
  if (parts.every((p) => p == null)) return null;
  return parts.reduce<number>((s, p) => s + (p ?? 0), 0);
}

export function sourced(
  man: number | null,
  source: AmountSource | null,
  note?: string
): SourcedAmount {
  return { man, source: man == null ? null : source, note };
}
