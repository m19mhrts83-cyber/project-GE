// node --experimental-strip-types --test tests/logPulse.test.ts
// 判断ログの演出：10件ごとの区切りをまたいだかの判定
import { test } from "node:test";
import assert from "node:assert/strict";
import { crossedMilestone } from "../lib/logPulse.ts";

test("区切りをまたいだときだけ、その区切りを返す", () => {
  assert.equal(crossedMilestone(9, 10), 10);
  assert.equal(crossedMilestone(8, 12), 10);
  assert.equal(crossedMilestone(10, 11), 0);
  assert.equal(crossedMilestone(3, 4), 0);
  assert.equal(crossedMilestone(19, 21), 20);
});

test("増えていない・区切りが不正なら 0", () => {
  assert.equal(crossedMilestone(10, 10), 0);
  assert.equal(crossedMilestone(12, 9), 0);
  assert.equal(crossedMilestone(0, 5, 0), 0);
});
