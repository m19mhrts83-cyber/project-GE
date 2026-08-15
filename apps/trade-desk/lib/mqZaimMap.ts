/**
 * Zaim（kurashift_finance_transactions）→ MQ 要素の割当
 */

export type MqElement =
  | "pq"
  | "vq"
  | "f"
  | "f_annual"
  | "cash_out"
  | "exclude";

export type MqAccountMapRow = {
  id?: string;
  business_line: "realestate" | "ai";
  category_match: string;
  subcategory_match: string;
  entity_match: "" | "personal" | "corporate";
  mq_element: MqElement;
  combine_treatment: "include" | "exclude_on_combined";
  priority: number;
  approved: boolean;
  note?: string | null;
};

export type FinanceTxnLite = {
  category: string | null;
  subcategory: string | null;
  entity: string | null;
  kind: string | null;
  txn_date: string | null;
  income_jpy: number | string | null;
  expense_jpy: number | string | null;
  /** 支払元・入金先・品目・メモ（高確度ヒューリスティック用） */
  from_account?: string | null;
  to_account?: string | null;
  description?: string | null;
  memo?: string | null;
};

export type MapResolveReason =
  | "account_map"
  | "kind_rent_income"
  | "heuristic_realestate"
  | "unmapped";

function yen(n: number | string | null | undefined): number {
  const v = Number(n);
  return Number.isFinite(v) ? v : 0;
}

function includesCI(hay: string, needle: string): boolean {
  if (!needle) return true;
  return hay.toLowerCase().includes(needle.toLowerCase());
}

/** 不動産口座・文言の高確度シグナル（曖昧なものは付けない） */
const RE_ACCOUNT_HINTS = [
  "アパート経営",
  "MUFG(アパート",
  "PayPay銀行",
  "滋賀銀行",
];
const RE_TEXT_HINTS = [
  "家賃",
  "賃貸",
  "不動産",
  "マンション",
  "管理費",
  "修繕",
  "固定資産税",
  "固都税",
  "火災保険",
  "ローン",
  "19.1",
  "19F",
  "Grandole",
  "キャラメル",
  "LEAF",
];

function blobOf(txn: FinanceTxnLite): string {
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

function hasReAccount(txn: FinanceTxnLite): boolean {
  const acc = `${txn.from_account || ""} ${txn.to_account || ""}`;
  return RE_ACCOUNT_HINTS.some((h) => acc.includes(h));
}

function hasReText(txn: FinanceTxnLite): boolean {
  const b = blobOf(txn);
  return RE_TEXT_HINTS.some((h) => b.includes(h));
}

function guessMqElement(txn: FinanceTxnLite): MqElement {
  const sub = txn.subcategory || "";
  const cat = txn.category || "";
  const inc = yen(txn.income_jpy);
  if (inc > 0 || txn.kind === "rent_income" || /家賃|19\.1/i.test(cat)) {
    return "pq";
  }
  if (/ローン/i.test(sub) || /ローン/i.test(cat)) return "cash_out";
  if (/固定資産|固都税|火災保険|保険/i.test(sub) || /固定資産|固都税/i.test(cat)) {
    return "f_annual";
  }
  if (/管理|外注/i.test(sub) || /管理費/i.test(cat)) return "vq";
  if (/修繕/i.test(sub) || /修繕/i.test(cat) || txn.kind === "repair") return "f";
  if (txn.kind === "rental_expense") return "f";
  return "f";
}

/** 優先度の低い数字が先。最初にマッチしたマップを採用 */
export function resolveMap(
  maps: MqAccountMapRow[],
  txn: FinanceTxnLite
): MqAccountMapRow | null {
  return resolveMapDetailed(maps, txn).map;
}

export function resolveMapDetailed(
  maps: MqAccountMapRow[],
  txn: FinanceTxnLite
): { map: MqAccountMapRow | null; reason: MapResolveReason } {
  const cat = txn.category || "";
  const sub = txn.subcategory || "";
  const ent = txn.entity || "";
  const sorted = [...maps]
    .filter((m) => m.approved)
    .sort(
      (a, b) =>
        a.priority - b.priority ||
        a.category_match.length - b.category_match.length
    );

  for (const m of sorted) {
    if (m.entity_match && m.entity_match !== ent) continue;
    if (!includesCI(cat, m.category_match)) continue;
    if (!includesCI(sub, m.subcategory_match)) continue;
    return { map: m, reason: "account_map" };
  }

  if (txn.kind === "rent_income") {
    return {
      map: {
        business_line: "realestate",
        category_match: "",
        subcategory_match: "",
        entity_match: "",
        mq_element: "pq",
        combine_treatment: "include",
        priority: 999,
        approved: true,
        note: "kind=rent_income",
      },
      reason: "kind_rent_income",
    };
  }

  const strong =
    txn.kind === "rental_expense" ||
    txn.kind === "repair" ||
    hasReAccount(txn) ||
    (hasReText(txn) && hasReAccount(txn)) ||
    (hasReText(txn) && /19|賃貸|家賃|不動産|マンション/i.test(cat));

  if (
    strong &&
    (hasReText(txn) ||
      hasReAccount(txn) ||
      txn.kind === "rental_expense" ||
      txn.kind === "repair")
  ) {
    return {
      map: {
        business_line: "realestate",
        category_match: "",
        subcategory_match: "",
        entity_match: "",
        mq_element: guessMqElement(txn),
        combine_treatment: "include",
        priority: 900,
        approved: true,
        note: "heuristic_realestate",
      },
      reason: "heuristic_realestate",
    };
  }

  return { map: null, reason: "unmapped" };
}

export type MonthBucket = {
  business_line: "realestate" | "ai";
  entity: "personal" | "corporate";
  period_month: string; // YYYY-MM-01
  pq: number;
  vq: number;
  f: number;
  f_annual: number;
  cash_out: number;
  cash_in: number;
};

export type AggregateResult = {
  buckets: MonthBucket[];
  unmapped: {
    category: string;
    subcategory: string;
    entity: string;
    count: number;
    amount: number;
  }[];
  skippedManualMonths: string[];
  loanMixedWarn: boolean;
  /** ヒューリスティックで不動産に寄せた件数 */
  heuristicRealestateCount: number;
};

export function monthStart(iso: string | null): string | null {
  if (!iso || iso.length < 7) return null;
  return `${iso.slice(0, 7)}-01`;
}

/**
 * 対象: entity personal|corporate、skip除外。
 * 家計β系はマップに無ければ未分類（事業取込対象外として金額集計のみ警告）。
 */
export function aggregateZaimToMq(
  txns: FinanceTxnLite[],
  maps: MqAccountMapRow[],
  opts?: { year?: number }
): AggregateResult {
  const bucketMap = new Map<string, MonthBucket>();
  const unmappedMap = new Map<
    string,
    { category: string; subcategory: string; entity: string; count: number; amount: number }
  >();
  let loanMixedWarn = false;
  let heuristicRealestateCount = 0;

  function bucketKey(line: string, entity: string, month: string) {
    return `${line}|${entity}|${month}`;
  }

  function getBucket(
    line: "realestate" | "ai",
    entity: "personal" | "corporate",
    month: string
  ): MonthBucket {
    const k = bucketKey(line, entity, month);
    let b = bucketMap.get(k);
    if (!b) {
      b = {
        business_line: line,
        entity,
        period_month: month,
        pq: 0,
        vq: 0,
        f: 0,
        f_annual: 0,
        cash_out: 0,
        cash_in: 0,
      };
      bucketMap.set(k, b);
    }
    return b;
  }

  for (const t of txns) {
    const ent = t.entity || "";
    if (ent !== "personal" && ent !== "corporate") continue;
    const month = monthStart(t.txn_date);
    if (!month) continue;
    if (opts?.year != null && !month.startsWith(String(opts.year))) continue;

    const inc = yen(t.income_jpy);
    const exp = yen(t.expense_jpy);
    const amount = inc > 0 ? inc : exp;
    if (amount <= 0) continue;

    const { map: hit, reason } = resolveMapDetailed(maps, t);
    if (!hit) {
      const cat = t.category || "";
      if (
        !/19|賃貸|家賃|不動産|AI|21F|マンション/i.test(cat) &&
        t.kind !== "rental_expense" &&
        t.kind !== "rent_income"
      ) {
        continue;
      }
      const uk = `${cat}|${t.subcategory || ""}|${ent}`;
      const u = unmappedMap.get(uk) || {
        category: cat,
        subcategory: t.subcategory || "",
        entity: ent,
        count: 0,
        amount: 0,
      };
      u.count += 1;
      u.amount += amount;
      unmappedMap.set(uk, u);
      continue;
    }

    if (reason === "heuristic_realestate") heuristicRealestateCount += 1;

    const b = getBucket(hit.business_line, ent, month);
    if (hit.mq_element === "pq") {
      b.pq += inc > 0 ? inc : 0;
      if (inc > 0) b.cash_in += inc;
    } else if (hit.mq_element === "vq") {
      b.vq += exp;
      b.cash_out += exp;
    } else if (hit.mq_element === "f") {
      b.f += exp;
      b.cash_out += exp;
    } else if (hit.mq_element === "f_annual") {
      b.f_annual += exp;
      b.cash_out += exp;
    } else if (hit.mq_element === "cash_out") {
      b.cash_out += exp;
      if ((t.subcategory || "").includes("ローン")) loanMixedWarn = true;
    } else if (hit.mq_element === "exclude") {
      /* skip */
    }
  }

  return {
    buckets: Array.from(bucketMap.values()),
    unmapped: Array.from(unmappedMap.values()).sort((a, b) => b.amount - a.amount),
    skippedManualMonths: [],
    loanMixedWarn,
    heuristicRealestateCount,
  };
}
