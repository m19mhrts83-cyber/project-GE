import { test } from "node:test";
import assert from "node:assert/strict";
import { buildCloseLeakDecisions, parseCloseLeak, pendingCards, type CloseLeakCard } from "../lib/closeLeak.ts";
import { normalizeDecision } from "../lib/decisionContract.ts";

const card = (id: string): CloseLeakCard => ({
  id, title: `タスク${id}`, confidence: "low", why: "送信記録あり",
  evidence: [{ folder: "P01_相手", subject: "件名", at: "2026-11-24T20:00:00+09:00" }],
});

test("壊れた・空の材料は null（0件と区別する）", () => {
  assert.equal(parseCloseLeak(null), null);
  assert.equal(parseCloseLeak("{bad"), null);
  assert.equal(parseCloseLeak('{"v":1}'), null);
  assert.equal(parseCloseLeak('{"v":1,"generated_at":"x","total":0,"cards":[]}')?.cards.length, 0);
});

test("判断済みの件は外す", () => {
  const snap = { v: 1, generated_at: "2026-11-25T19:30:00+09:00", total: 3, cards: [card("a"), card("b"), card("c")] };
  assert.deepEqual(pendingCards(snap, ["b"]).map((c) => c.id), ["a", "c"]);
});

test("済み→close・残す→defer。bulk と origin=close_leak で reflect が拾える形", () => {
  const rows = buildCloseLeakDecisions([card("a"), card("b"), card("c")], { a: "close", b: "keep" }, "n1", "2026-11-25T00:00:00Z");
  assert.deepEqual(rows.map((r) => r.action), ["close", "defer"]);
  const p = rows[0].payload as { bulk: boolean; origin: string; evidence: unknown[] };
  assert.equal(p.bulk, true);
  assert.equal(p.origin, "close_leak");
  assert.equal(p.evidence.length, 1);
  for (const r of rows) assert.equal(normalizeDecision(r).ok, true);
});
