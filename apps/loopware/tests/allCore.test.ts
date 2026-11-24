import { test } from "node:test";
import assert from "node:assert/strict";
import { adoptSuggestions, applyFilter, cleanupItem, countBy, mailItem, sortItems, topicItem } from "../lib/allCore.ts";

const mail = (o: Record<string, unknown>) =>
  mailItem({ id: "m1", subject: "件名", who: "相手", lane: "general", postedToSlack: false, hesitatedAt: null, score: null, receivedAt: null, summary: "", ...o } as never);
const clean = (o: Record<string, unknown>) =>
  cleanupItem({ id: "c1", title: "t", sender: "s", summary: "", suggest: "keep", why: "w", age_days: 10, deadline: null, priority: 1, gmail_url: "", ...o } as never, "2026-11-24");

test("パートナーと支払い失敗は重要度『高』", () => {
  assert.equal(mail({ lane: "partner" }).level, 3);
  assert.equal(mail({ subject: "引き落としができませんでした" }).level, 3);
  assert.equal(mail({ postedToSlack: true }).level, 2);
  assert.equal(mail({}).level, 1);
});

test("片付けは期限が近い・優先度が高いと『高』、おすすめどおりの提案を持つ", () => {
  assert.equal(clean({ deadline: "2026-11-30" }).level, 3);
  assert.equal(clean({ priority: 4 }).level, 3);
  assert.equal(clean({ suggest: "close" }).level, 1);
  assert.equal(clean({ suggest: "close" }).suggest, "close");
  assert.equal(clean({ suggest: "keep" }).suggest, "later");
});

test("お題は推しの案が提案になる。無ければ提案なし", () => {
  const t = { id: "t1", title: "x", topicText: "[Slack] 起票して", proposals: [{ index: 1, label: "追記", body: "" }, { index: 2, label: "別", body: "" }] };
  assert.equal(topicItem({ ...t, starred: 2 } as never).suggest, "pick:2");
  assert.equal(topicItem(t as never).suggest, null);
});

test("重要度の高い順に並べ、絞り込みと件数が合う", () => {
  const items = sortItems([mail({ id: "a" }), mail({ id: "b", lane: "partner" }), clean({ id: "z", suggest: "close" })]);
  assert.equal(items[0].id, "b");
  assert.equal(applyFilter(items, { genre: "cleanup", level: 0 }).length, 1);
  assert.equal(applyFilter(items, { genre: "all", level: 3 }).length, 1);
  const n = countBy(items);
  assert.equal(n.total, 3);
  assert.equal(n.level[3], 1);
});

test("提案どおりは未選択の行にだけ入り、選び直しを上書きしない", () => {
  const items = [clean({ id: "a", suggest: "close" }), clean({ id: "b", suggest: "drop" }), mail({ id: "m" })];
  const r = adoptSuggestions(items, { "cleanup:b": "later" });
  assert.deepEqual(r, { "cleanup:a": "close", "cleanup:b": "later" });
});
