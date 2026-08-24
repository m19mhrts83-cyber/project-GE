import assert from "node:assert/strict";
import {
  afterTax,
  cashFlowBridge,
  debtPaybackYears,
  equityRatio,
  pretaxProfit,
  straightLineDepMan,
  taxOnPretax,
} from "./reBusinessPlMath";

// 手計算: 収入100 − 経費30 − 償却20 − 利息10 = 税前40 → 税8 → 税後32
// CF = 32 + 20 + 8 − 0 − 25 = 35
{
  const pretax = pretaxProfit(100, 30, 20, 10);
  assert.equal(pretax.man, 40);
  const tax = taxOnPretax(40, 0.2);
  assert.equal(tax.man, 8);
  const after = afterTax(40, 8);
  assert.equal(after.man, 32);
  const cf = cashFlowBridge({
    afterTax: 32,
    depreciation: 20,
    tax: 8,
    taxPaid: 0,
    principal: 25,
  });
  assert.equal(cf.man, 35);
}

// 赤字の税金は0
{
  assert.equal(taxOnPretax(-10, 0.2).man, 0);
}

// 定額償却
{
  // 4700万 / 47年 = 100万/年
  assert.equal(straightLineDepMan(47_000_000, 47), 100);
}

// 指標
{
  assert.equal(equityRatio(30, 100), 0.3);
  assert.equal(debtPaybackYears(200, 40), 5);
}

console.log("reBusinessPl.selftest: ok");
