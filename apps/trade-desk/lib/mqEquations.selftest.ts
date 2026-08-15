/**
 * Run: cd apps/trade-desk && npx --yes tsx lib/mqEquations.selftest.ts
 */
import {
  computeMq,
  gainIgnoresPrincipalRepayment,
  monthlyAllocatedF,
  sumMqInputs,
  yearlyFFromMonthlyRows,
} from "./mqEquations";

function assert(cond: boolean, msg: string) {
  if (!cond) throw new Error(msg);
}

// 研修シート型の例（IMG_1056）: PQ=825 VQ=454 MQ=371 F=332 G=39
const demo = computeMq({ pq: 825, vq: 454, f: 332, q: 1 });
assert(demo.mq === 371, `mq want 371 got ${demo.mq}`);
assert(demo.g === 39, `g want 39 got ${demo.g}`);
assert(demo.equationOk, "enterprise equation");
assert(Math.abs((demo.mOverP ?? 0) - 371 / 825) < 1e-9, "m/p");
assert(Math.abs((demo.gOverPq ?? 0) - 39 / 825) < 1e-9, "g/pq");

// Q未入力 → 単価なし
const noQ = computeMq({ pq: 100, vq: 20, f: 30, q: null });
assert(noQ.p == null && noQ.v == null && noQ.m == null, "no unit without q");

// 元本を F に入れると G が変わる（禁止パターンの検知）
assert(
  gainIgnoresPrincipalRepayment({ pq: 100, vq: 10, f: 40, q: 5 }, 10),
  "principal in F must change G (detect misuse)"
);

// 合算は単純加算（二重計上は呼び出し側で除外済み前提）
const summed = sumMqInputs([
  { pq: 50, vq: 10, f: 20, q: 2 },
  { pq: 30, vq: 5, f: 10, q: 1 },
]);
assert(summed.pq === 80 && summed.vq === 15 && summed.f === 30, "sum");
assert(summed.q === 3, "sum q");

// 年額÷12 按分（月次評価）
assert(monthlyAllocatedF(10, 120) === 20, "monthly allocate");
assert(
  yearlyFFromMonthlyRows([
    { f: 10, f_annual: 120 },
    { f: 10, f_annual: 120 },
  ]) === 140,
  "yearly must not 12x annual"
);

console.log("mqEquations.selftest: ok");
