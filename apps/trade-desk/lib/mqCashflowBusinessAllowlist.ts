/**
 * 資金繰り表に載せる Zaim 事業費目のホワイトリスト。
 * 該当外（ライフプラン系など）は資金繰りから除外する。
 */

import type { FinanceTxnLite } from "./mqZaimMap";

export type BusinessAllowSide = "income" | "expense";

export type BusinessAllowHit = {
  side: BusinessAllowSide;
  /** 支出の振り分けヒント: delta19f = Δ19F 内訳ヒューリスティック / expense_flat = 経費固定 */
  expenseMode: "delta19f" | "expense_flat" | null;
  /** 取込・表示の既定主体（カテゴリに個人/法人が無いとき） */
  defaultEntity: "personal" | "corporate" | null;
  label: string;
};

function cat(txn: FinanceTxnLite): string {
  return String(txn.category || "");
}

function sub(txn: FinanceTxnLite): string {
  return String(txn.subcategory || "");
}

function includesCI(hay: string, needle: string): boolean {
  return hay.toLowerCase().includes(needle.toLowerCase());
}

/** Δ19F 賃貸経営（個人事業／法人）。カテゴリに 19F があれば事業費目とみなす */
function isDelta19F(c: string): boolean {
  return includesCI(c, "19F") || includesCI(c, "賃貸経営");
}

/** Δ21F AIリスキリング */
function isDelta21F(c: string): boolean {
  return includesCI(c, "21F") && includesCI(c, "AI");
}

/** γ.6.2C 自己投資・寄付 × 不動産投資関連(経費) */
function isGammaRealestateExpense(c: string, s: string): boolean {
  if (!includesCI(c, "6.2C") && !includesCI(c, "自己投資")) return false;
  return (
    includesCI(s, "不動産投資") ||
    includesCI(s, "不動産投資 関連") ||
    (includesCI(s, "不動産") && includesCI(s, "経費"))
  );
}

/** βご褒美 × 不動産経費 */
function isBetaRealestateExpense(c: string, s: string): boolean {
  if (!includesCI(c, "ご褒美") && !includesCI(c, "20.2S")) return false;
  return includesCI(s, "不動産");
}

/** 事業ホワイトリストに当たればヒット、否则 null */
export function matchBusinessAllowlist(
  txn: FinanceTxnLite
): BusinessAllowHit | null {
  const c = cat(txn);
  const s = sub(txn);
  const inc = Number(txn.income_jpy) || 0;
  const exp = Number(txn.expense_jpy) || 0;

  // —— 収入 ——
  if (inc > 0) {
    if (includesCI(c, "家賃収入") || includesCI(c, "19.1")) {
      const corp = includesCI(c, "法人");
      const pers = includesCI(c, "個人");
      return {
        side: "income",
        expenseMode: null,
        defaultEntity: corp ? "corporate" : pers ? "personal" : "personal",
        label: "家賃収入",
      };
    }
    if (
      includesCI(c, "不労所得") &&
      (includesCI(c, "売却") || includesCI(c, "譲渡"))
    ) {
      return {
        side: "income",
        expenseMode: null,
        defaultEntity: "personal",
        label: "不労所得（売却）",
      };
    }
    if (
      includesCI(c, "不労所得") &&
      (includesCI(c, "LUUP") || includesCI(c, "ループ") || includesCI(c, "19.3"))
    ) {
      return {
        side: "income",
        expenseMode: null,
        defaultEntity: "personal",
        label: "不労所得ループ",
      };
    }
    if (
      includesCI(c, "事業収入") &&
      (includesCI(c, "不動産") || includesCI(c, "19.4"))
    ) {
      return {
        side: "income",
        expenseMode: null,
        defaultEntity: "personal",
        label: "事業収入（不動産）",
      };
    }
    if (
      (includesCI(c, "不動産収入") && includesCI(c, "AI")) ||
      (includesCI(c, "不動産") && includesCI(c, "AI") && includesCI(c, "収入"))
    ) {
      return {
        side: "income",
        expenseMode: null,
        defaultEntity: "personal",
        label: "不動産収入（AI）",
      };
    }
    if (includesCI(c, "保険金") || includesCI(c, "19.6")) {
      return {
        side: "income",
        expenseMode: null,
        defaultEntity: "personal",
        label: "保険金",
      };
    }
    return null;
  }

  // —— 支出 ——
  if (exp > 0) {
    if (isDelta19F(c)) {
      const corp = includesCI(c, "法人");
      const pers = includesCI(c, "個人");
      return {
        side: "expense",
        expenseMode: "delta19f",
        defaultEntity: corp ? "corporate" : pers ? "personal" : null,
        label: "Δ19F 賃貸経営",
      };
    }
    if (isDelta21F(c)) {
      return {
        side: "expense",
        expenseMode: "expense_flat",
        defaultEntity: "personal",
        label: "Δ21F AIリスキリング",
      };
    }
    if (isGammaRealestateExpense(c, s)) {
      return {
        side: "expense",
        expenseMode: "expense_flat",
        defaultEntity: "personal",
        label: "γ自己投資・不動産関連",
      };
    }
    if (isBetaRealestateExpense(c, s)) {
      return {
        side: "expense",
        expenseMode: "expense_flat",
        defaultEntity: "personal",
        label: "βご褒美・不動産",
      };
    }
    return null;
  }

  return null;
}

export function isBusinessCashflowTxn(txn: FinanceTxnLite): boolean {
  return matchBusinessAllowlist(txn) != null;
}
