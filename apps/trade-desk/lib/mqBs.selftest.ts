import {
  combineBs,
  emptyBs,
  isBsBalanced,
  isBsComplete,
  missingBsFields,
  monthEndDate,
  normalizeBs,
  resolveCurrentProfit,
  sumAssets,
  sumLiabEquity,
} from "./mqBs";

function assert(cond: boolean, msg: string) {
  if (!cond) throw new Error(msg);
}

const sample = normalizeBs({
  cash: 39,
  receivables: 120,
  inventory: 153,
  fixed_assets: 52,
  liabilities_st: 0,
  liabilities_lt: 168,
  capital: 261,
  retained_earnings: -104,
  current_profit: 39,
});

assert(sumAssets(sample) === 364, "assets");
assert(sumLiabEquity(sample) === 364, "liab+eq");
assert(isBsComplete(sample, { requireInventory: true }), "complete w/ inv");
assert(isBsBalanced(sample, { requireInventory: true }), "balanced");

const incomplete = normalizeBs({ cash: 10 });
assert(!isBsComplete(incomplete), "incomplete");
assert(!isBsBalanced(incomplete), "unbalanced when incomplete");
assert(missingBsFields(incomplete).includes("fixed_assets"), "missing fixed");

// 賃貸: 棚卸は必須にしない
const rental = normalizeBs({
  cash: 100,
  receivables: 0,
  inventory: null,
  fixed_assets: 5000,
  liabilities_st: 0,
  liabilities_lt: 4000,
  capital: 1000,
  retained_earnings: 50,
  current_profit: 50,
});
assert(isBsComplete(rental), "rental complete without inventory");
assert(isBsBalanced(rental), "rental balanced");

// 合算: 片方 null なら捏造しない
const a = normalizeBs({ cash: 10, receivables: 0, fixed_assets: 100, liabilities_st: 0, liabilities_lt: 50, capital: 50, retained_earnings: 5, current_profit: 5 });
const b = normalizeBs({ cash: null, receivables: 0, fixed_assets: 200, liabilities_st: 0, liabilities_lt: 100, capital: 100, retained_earnings: 0, current_profit: 0 });
const both = combineBs(a, b);
assert(both != null && both.cash == null, "combine does not invent cash");
assert(both != null && both.fixed_assets === 300, "combine sums known");

const onlyA = combineBs(a, null);
assert(onlyA != null && onlyA.cash === 10, "single side passthrough");

const g = resolveCurrentProfit(emptyBs(), 39);
assert(g.value === 39 && g.fromMq === true, "G from MQ");
const g2 = resolveCurrentProfit(normalizeBs({ current_profit: 40 }), 39);
assert(g2.value === 40 && g2.fromMq === false, "G from BS");

assert(monthEndDate("2026-08") === "2026-08-31", "month end");
assert(monthEndDate("2026-02") === "2026-02-28", "feb");

console.log("mqBs.selftest: ok");
