import type { FinanceTxnLite } from "./mqZaimMap";
import type { CashflowBucketKey } from "./mqCashflowColumns";
import { BUCKET_TO_COLUMN, type CashflowColumnKey } from "./mqCashflowColumns";

export type CashflowClassifyRuleRow = {
  id?: string;
  business_line: string;
  entity_match: "" | "personal" | "corporate";
  category_match: string;
  subcategory_match: string;
  cashflow_column: string;
  note?: string | null;
};

export type TxnOverrideRow = {
  txn_id: number | string;
  business_line: string;
  cashflow_column: string;
};

export type ClassifyReason =
  | "override"
  | "learned_rule"
  | "heuristic"
  | "heuristic_loan";

export type ClassifyResult = {
  column: CashflowColumnKey;
  bucket: CashflowBucketKey | null;
  isLoan: boolean;
  reason: ClassifyReason;
  detail?: string;
};

function includesCI(hay: string, needle: string): boolean {
  if (!needle) return true;
  return hay.toLowerCase().includes(needle.toLowerCase());
}

function matchesAny(hay: string, needles: readonly string[]): boolean {
  const h = hay.toLowerCase();
  return needles.some((n) => h.includes(n.toLowerCase()));
}

/** 科目・摘要・口座名を含む全文（mqZaimMap.blobOf と同系） */
export function txnTextBlob(txn: FinanceTxnLite): string {
  return [
    txn.category,
    txn.subcategory,
    txn.description,
    txn.memo,
    txn.from_account,
    txn.to_account,
  ]
    .filter(Boolean)
    .join(" ");
}

/** 火災・地震保険の支払 */
export function detectFireInsurance(text: string): boolean {
  const b = text.toLowerCase();
  if (b.includes("火災保険") || b.includes("地震保険")) return true;
  if (b.includes("火災") && b.includes("保険")) return true;
  return false;
}

function isAcquisitionContext(text: string): boolean {
  return /取得|新規加入|契約時|引渡|購入時|ローン実行|諸費用|取得時|初回/.test(
    text
  );
}

/** 既存 mqCashflow.ts と同系統のヒューリスティック */
export function classifyExpenseTxnHeuristic(txn: FinanceTxnLite): {
  isLoan: boolean;
  bucket: CashflowBucketKey | null;
} {
  const blob = txnTextBlob(txn).toLowerCase();

  const isLoan = matchesAny(blob, [
    "ローン",
    "返済",
    "借入返済",
    "支払（ローン",
    "融資返済",
  ]);
  if (isLoan) return { isLoan: true, bucket: null };

  if (matchesAny(blob, ["税理士"])) {
    if (matchesAny(blob, ["報酬", "顧問", "顧問料"])) {
      return { isLoan: false, bucket: "taxAccountant" };
    }
    return { isLoan: false, bucket: "acquisition" };
  }

  if (detectFireInsurance(blob)) {
    return {
      isLoan: false,
      bucket: isAcquisitionContext(blob) ? "acquisition" : "annualTax",
    };
  }

  if (matchesAny(blob, ["手数料", "保証料", "登記", "印紙", "融資"])) {
    return { isLoan: false, bucket: "acquisition" };
  }

  if (
    matchesAny(blob, [
      "固定資産税",
      "都市計画税",
      "固都税",
      "税金",
      "租税",
      "租税公課",
    ])
  ) {
    return { isLoan: false, bucket: "annualTax" };
  }

  if (
    matchesAny(blob, [
      "管理費",
      "共益",
      "水道",
      "電気",
      "インターネット",
      "ネット",
      "通信",
    ])
  ) {
    return { isLoan: false, bucket: "management" };
  }

  if (
    matchesAny(blob, [
      "修繕",
      "リフォーム",
      "原状回復",
      "改修",
      "クロス",
      "設備交換",
      "工事",
    ])
  ) {
    return { isLoan: false, bucket: "repair" };
  }

  if (matchesAny(blob, ["広告", "宣伝", "募集", "掲載"])) {
    return { isLoan: false, bucket: "advertising" };
  }

  return { isLoan: false, bucket: "expense" };
}

function columnFromBucket(bucket: CashflowBucketKey | null): CashflowColumnKey {
  if (!bucket) return "expense";
  return BUCKET_TO_COLUMN[bucket];
}

function ruleMatchesTxn(
  rule: CashflowClassifyRuleRow,
  txn: FinanceTxnLite,
  businessLine: string
): boolean {
  if (rule.business_line !== businessLine) return false;
  const ent = txn.entity || "";
  if (rule.entity_match && rule.entity_match !== ent) return false;
  const cat = txn.category || "";
  const sub = txn.subcategory || "";
  if (!includesCI(cat, rule.category_match)) return false;
  if (rule.subcategory_match && !includesCI(sub, rule.subcategory_match)) {
    return false;
  }
  return true;
}

function findLearnedRule(
  txn: FinanceTxnLite,
  businessLine: string,
  rules: CashflowClassifyRuleRow[]
): CashflowClassifyRuleRow | null {
  const hits = rules.filter((r) => ruleMatchesTxn(r, txn, businessLine));
  if (hits.length === 0) return null;
  // サブカテゴリ完全一致を優先
  hits.sort((a, b) => {
    const sa = a.subcategory_match ? 1 : 0;
    const sb = b.subcategory_match ? 1 : 0;
    return sb - sa;
  });
  return hits[0] ?? null;
}

function parseColumnKey(raw: string): CashflowColumnKey | null {
  const allowed: CashflowColumnKey[] = [
    "sales",
    "borrow_lt",
    "borrow_st",
    "borrow_officer",
    "repair",
    "advertising",
    "expense",
    "management",
    "acquisition",
    "tax_accountant",
    "loan_repayment",
    "annual_tax",
    "interest_yearend",
    "tax_payment",
    "action_inflow",
  ];
  return (allowed as string[]).includes(raw) ? (raw as CashflowColumnKey) : null;
}

/** 取引 txn_id → 列上書き */
export function buildOverrideMap(
  rows: TxnOverrideRow[],
  businessLine: string
): Map<number, CashflowColumnKey> {
  const m = new Map<number, CashflowColumnKey>();
  for (const r of rows) {
    if (r.business_line !== businessLine) continue;
    const col = parseColumnKey(String(r.cashflow_column));
    const id = Number(r.txn_id);
    if (col && Number.isFinite(id)) m.set(id, col);
  }
  return m;
}

export function resolveCashflowColumn(
  txn: FinanceTxnLite,
  opts: {
    businessLine: string;
    overrides: Map<number, CashflowColumnKey>;
    rules: CashflowClassifyRuleRow[];
  }
): ClassifyResult {
  const txnId = txn.id != null ? Number(txn.id) : NaN;
  if (Number.isFinite(txnId) && opts.overrides.has(txnId)) {
    const col = opts.overrides.get(txnId)!;
    return {
      column: col,
      bucket: null,
      isLoan: col === "loan_repayment",
      reason: "override",
      detail: `txn override → ${col}`,
    };
  }

  const learned = findLearnedRule(txn, opts.businessLine, opts.rules);
  if (learned) {
    const col = parseColumnKey(learned.cashflow_column);
    if (col) {
      return {
        column: col,
        bucket: null,
        isLoan: col === "loan_repayment",
        reason: "learned_rule",
        detail: `rule: ${learned.category_match}/${learned.subcategory_match}`,
      };
    }
  }

  const inc = Number(txn.income_jpy) || 0;
  if (inc > 0) {
    return {
      column: "sales",
      bucket: null,
      isLoan: false,
      reason: "heuristic",
      detail: "income",
    };
  }

  const h = classifyExpenseTxnHeuristic(txn);
  if (h.isLoan) {
    return {
      column: "loan_repayment",
      bucket: null,
      isLoan: true,
      reason: "heuristic_loan",
    };
  }

  return {
    column: columnFromBucket(h.bucket),
    bucket: h.bucket,
    isLoan: false,
    reason: "heuristic",
    detail: h.bucket ?? "expense",
  };
}

/** 再分類時に学習ルール upsert 用ペイロード */
export function buildLearnRuleFromTxn(
  txn: FinanceTxnLite,
  businessLine: string,
  cashflowColumn: CashflowColumnKey,
  sourceTxnId?: number
): Omit<CashflowClassifyRuleRow, "id"> {
  return {
    business_line: businessLine,
    entity_match: (txn.entity === "personal" || txn.entity === "corporate"
      ? txn.entity
      : "") as "" | "personal" | "corporate",
    category_match: String(txn.category || "").slice(0, 200),
    subcategory_match: String(txn.subcategory || "").slice(0, 200),
    cashflow_column: cashflowColumn,
    note: sourceTxnId ? `learned from txn ${sourceTxnId}` : "learned",
  };
}
