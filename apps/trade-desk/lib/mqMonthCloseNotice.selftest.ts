import assert from "node:assert/strict";
import {
  isMqMonthCloseWindow,
  mqMonthCloseNotice,
  previousCalendarMonth,
} from "./mqMonthCloseNotice";
import { sumLoanTrackerLt } from "./mqLoanSuggest";
import { qFieldLabel } from "./mqPolicy";

assert.equal(qFieldLabel("ai"), "Q（案件数）");
assert.equal(qFieldLabel("realestate"), "Q（稼働戸月）");

assert.equal(
  sumLoanTrackerLt([
    { balance_jpy: 1000 },
    { balance_jpy: 2500 },
    { balance_jpy: null },
  ]),
  3500
);
assert.equal(sumLoanTrackerLt([]), null);

// 固定時刻: 2026-08-05 JST 付近 → ウィンドウ内・対象 2026-07
const aug5 = new Date("2026-08-05T03:00:00+09:00");
assert.equal(previousCalendarMonth(aug5), "2026-07");
assert.equal(isMqMonthCloseWindow(aug5), true);
const n1 = mqMonthCloseNotice({ now: aug5, hasFacts: true });
assert.equal(n1.show, true);
assert.equal(n1.targetMonth, "2026-07");

const n2 = mqMonthCloseNotice({
  now: aug5,
  acked: { "2026-07": "2026-08-02T00:00:00Z" },
});
assert.equal(n2.show, false);

const aug20 = new Date("2026-08-20T12:00:00+09:00");
assert.equal(isMqMonthCloseWindow(aug20), false);
assert.equal(mqMonthCloseNotice({ now: aug20 }).show, false);

console.log("mqMonthCloseNotice.selftest: ok");
