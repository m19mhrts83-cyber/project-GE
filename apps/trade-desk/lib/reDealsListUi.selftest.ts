/**
 * Run: npx tsx lib/reDealsListUi.selftest.ts
 */
import {
  DEALS_PAGE_SIZE,
  dealTitleMatches,
  filterDealsByTitle,
  pageForDealId,
  paginateDeals,
} from "./reDealsListUi";

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) throw new Error(msg);
}

const deals = Array.from({ length: 87 }, (_, i) => ({
  id: `d${i + 1}`,
  title: i === 41 ? "大阪市東成区 収益マンション" : `候補物件 ${i + 1}号室`,
}));

assert(DEALS_PAGE_SIZE === 20, "page size 20");
assert(dealTitleMatches("大阪市東成区 収益マンション", "東成"), "partial title");
assert(dealTitleMatches("大阪市東成区 収益マンション", "  東成  "), "trim query");
assert(!dealTitleMatches("大阪市東成区 収益マンション", "名古屋"), "no match");
assert(dealTitleMatches("Foo", ""), "empty query matches all");

const hit = filterDealsByTitle(deals, "東成");
assert(hit.length === 1 && hit[0].id === "d42", "search finds title");

const none = filterDealsByTitle(deals, "存在しない件名XYZ");
assert(none.length === 0, "no false positives");

const p1 = paginateDeals(deals, 1);
assert(p1.slice.length === 20 && p1.from === 1 && p1.to === 20, "page 1");
assert(p1.pageCount === 5, "87 rows → 5 pages");

const p5 = paginateDeals(deals, 5);
assert(p5.slice.length === 7 && p5.from === 81 && p5.to === 87, "last page remainder");
assert(paginateDeals(deals, 99).page === 5, "clamp high page");
assert(paginateDeals(deals, 0).page === 1, "clamp low page");
assert(paginateDeals([], 1).from === 0 && paginateDeals([], 1).to === 0, "empty");

assert(pageForDealId(deals, "d42") === 3, "highlight on page 3");
assert(pageForDealId(deals, "missing") === 1, "unknown id → 1");

console.log("reDealsListUi.selftest: ok");
