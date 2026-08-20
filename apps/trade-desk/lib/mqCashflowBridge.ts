/** 資金繰り列 → MQ / 現金 / B/S（config/mq_cashflow_column_bridge.yaml と同期） */

import type { CashflowColumnKey } from "./mqCashflowColumns";

export type MqBridgeElement = "pq" | "vq" | "f" | "f_annual" | null;
export type MqBridgeCash = "in" | "out" | "end" | null;
export type MqBridgeBs =
  | "cash"
  | "liabilities_lt"
  | "liabilities_st"
  | "liabilities_lt_down"
  | "fixed_assets"
  | null;

export type CashflowBridgeRule = {
  label: string;
  mq: MqBridgeElement;
  cash: MqBridgeCash;
  bs?: MqBridgeBs;
};

export const CASHFLOW_COLUMN_BRIDGE: Record<
  Exclude<CashflowColumnKey, never>,
  CashflowBridgeRule
> = {
  sales: { label: "売上", mq: "pq", cash: "in" },
  borrow_lt: { label: "長期借入", mq: null, cash: "in", bs: "liabilities_lt" },
  borrow_st: { label: "短期借入", mq: null, cash: "in", bs: "liabilities_st" },
  borrow_officer: {
    label: "個人借入",
    mq: null,
    cash: "in",
    bs: "liabilities_st",
  },
  repair: { label: "修繕", mq: "f", cash: "out" },
  advertising: { label: "広告", mq: "f", cash: "out" },
  expense: { label: "経費", mq: "f", cash: "out" },
  management: { label: "管理費", mq: "vq", cash: "out" },
  acquisition: { label: "取得時", mq: "f", cash: "out", bs: "fixed_assets" },
  tax_accountant: { label: "税理士", mq: "f", cash: "out" },
  loan_repayment: {
    label: "返済",
    mq: null,
    cash: "out",
    bs: "liabilities_lt_down",
  },
  annual_tax: { label: "年払・税", mq: "f_annual", cash: "out" },
  interest_yearend: { label: "利息（期末）", mq: "f", cash: "out" },
  tax_payment: { label: "税金支払", mq: null, cash: "out" },
  action_inflow: {
    label: "処置（計画）",
    mq: null,
    cash: "in",
    bs: "liabilities_st",
  },
};

export function bridgeFor(col: CashflowColumnKey): CashflowBridgeRule {
  return CASHFLOW_COLUMN_BRIDGE[col];
}
