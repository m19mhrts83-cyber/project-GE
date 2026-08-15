/**
 * Run via: npx tsx lib/mqZaimMap.selftest.ts
 */
import {
  aggregateZaimToMq,
  resolveMap,
  resolveMapDetailed,
  type MqAccountMapRow,
} from "./mqZaimMap";

function assert(cond: boolean, msg: string) {
  if (!cond) throw new Error(msg);
}

const maps: MqAccountMapRow[] = [
  {
    business_line: "realestate",
    category_match: "19.1",
    subcategory_match: "",
    entity_match: "",
    mq_element: "pq",
    combine_treatment: "include",
    priority: 10,
    approved: true,
  },
  {
    business_line: "realestate",
    category_match: "賃貸",
    subcategory_match: "外注管理",
    entity_match: "",
    mq_element: "vq",
    combine_treatment: "include",
    priority: 20,
    approved: true,
  },
  {
    business_line: "realestate",
    category_match: "賃貸",
    subcategory_match: "ローン",
    entity_match: "",
    mq_element: "cash_out",
    combine_treatment: "include",
    priority: 5,
    approved: true,
  },
  {
    business_line: "realestate",
    category_match: "賃貸",
    subcategory_match: "固定資産",
    entity_match: "",
    mq_element: "f_annual",
    combine_treatment: "include",
    priority: 15,
    approved: true,
  },
];

const hit = resolveMap(maps, {
  category: "19.1 家賃収入(個人)",
  subcategory: "-",
  entity: "personal",
  kind: "rent_income",
  txn_date: "2026-03-15",
  income_jpy: 100000,
  expense_jpy: 0,
});
assert(hit?.mq_element === "pq", "rent pq");

const agg = aggregateZaimToMq(
  [
    {
      category: "19.1 家賃収入(個人)",
      subcategory: "-",
      entity: "personal",
      kind: "rent_income",
      txn_date: "2026-03-10",
      income_jpy: 200000,
      expense_jpy: 0,
    },
    {
      category: "δ.19F.賃貸経営(個人事業)",
      subcategory: "[不]外注管理費(個人事業)",
      entity: "personal",
      kind: "rental_expense",
      txn_date: "2026-03-12",
      income_jpy: 0,
      expense_jpy: 10000,
    },
    {
      category: "δ.19F.賃貸経営(個人事業)",
      subcategory: "ローン返済(個人事業)",
      entity: "personal",
      kind: "rental_expense",
      txn_date: "2026-03-20",
      income_jpy: 0,
      expense_jpy: 80000,
    },
    {
      category: "δ.19F.賃貸経営(個人事業)",
      subcategory: "[不]租税公課,固定資産税(個人事業)",
      entity: "personal",
      kind: "rental_expense",
      txn_date: "2026-03-05",
      income_jpy: 0,
      expense_jpy: 120000,
    },
  ],
  maps,
  { year: 2026 }
);

assert(agg.buckets.length === 1, "one bucket");
const b = agg.buckets[0];
assert(b.pq === 200000, `pq ${b.pq}`);
assert(b.vq === 10000, `vq ${b.vq}`);
assert(b.f_annual === 120000, `f_annual ${b.f_annual}`);
assert(b.f === 0, "loan not in f");
assert(b.cash_out === 10000 + 80000 + 120000, "cash out");
assert(agg.loanMixedWarn, "loan warn");

// ヒューリスティック: 口座+文言で不動産に寄せる
const heur = resolveMapDetailed([], {
  category: "その他",
  subcategory: "管理費",
  entity: "corporate",
  kind: "other_expense",
  txn_date: "2026-04-01",
  income_jpy: 0,
  expense_jpy: 5000,
  from_account: "★PayPay銀行",
  description: "賃貸管理",
});
assert(heur.reason === "heuristic_realestate", "heuristic reason");
assert(heur.map?.business_line === "realestate", "heuristic line");
assert(heur.map?.mq_element === "vq", "heuristic vq");

// 曖昧な家計は未分類
const vague = resolveMapDetailed([], {
  category: "食費",
  subcategory: "外食",
  entity: "personal",
  kind: "other_expense",
  txn_date: "2026-04-01",
  income_jpy: 0,
  expense_jpy: 1000,
  from_account: "★名古屋銀行",
});
assert(vague.map == null, "vague unmapped");

console.log("mqZaimMap.selftest: ok");
