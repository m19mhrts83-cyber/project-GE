import { test } from "node:test";
import assert from "node:assert/strict";
import { buildCleanupDecisions, addDaysIso, actLabel, groupOf, type CleanupCard } from "../lib/cleanupBulk.ts";
import { normalizeDecision } from "../lib/decisionContract.ts";

const card = (id: string, suggest: CleanupCard["suggest"] = "keep"): CleanupCard => ({
  id, title: `タスク${id}`, sender: "S", subject: "", mail_date: "2026-07-10", summary: "", gmail_url: "", due: null,
  added_at: "2026-11-16", age_days: 130, suggest, why: "理由",
});

test("選んだものだけ記録し、keep は defer になる", () => {
  const rows = buildCleanupDecisions(
    [card("a", "close"), card("b"), card("c"), card("d")],
    { a: { act: "close" }, b: { act: "keep" }, c: { act: "reschedule", due: "2026-11-24" } },
    "n1",
    "2026-11-17T00:00:00Z",
  );
  assert.deepEqual(rows.map((r) => r.action), ["close", "defer", "reschedule"]);
  assert.equal((rows[2].payload as { due: string }).due, "2026-11-24");
  assert.equal((rows[0].payload as { followed_suggest: boolean }).followed_suggest, true);
  for (const r of rows) assert.ok(normalizeDecision(r).ok);
});

test("日付のない reschedule は記録しない", () => {
  assert.equal(buildCleanupDecisions([card("a")], { a: { act: "reschedule" } }, "n", "2026-11-17T00:00:00Z").length, 0);
});

test("318 の判断依頼は印付きで記録し、契約を通る", () => {
  const c318: CleanupCard = { ...card("x"), origin: "318", due: "2026-11-20", prev: "前回: 残す（2026-11-01）" };
  const rows = buildCleanupDecisions([c318, card("y")], { x: { act: "keep" }, y: { act: "close" } }, "n", "2026-11-23T00:00:00Z");
  const p = rows[0].payload as { label: string; origin?: string; bulk: boolean };
  assert.equal(p.label, "318判断依頼");
  assert.equal(p.origin, "318");
  assert.equal(p.bulk, true);
  assert.equal(rows[0].surface, "todoist_313");
  assert.equal((rows[1].payload as { label: string }).label, "スター起票");
  for (const r of rows) assert.ok(normalizeDecision(r).ok);
});

test("313 週の整理: 済み・やめる・残すだけ記録し、印と呼び方が付く", () => {
  const c = (id: string): CleanupCard => ({ ...card(id, "drop"), origin: "313", why: "30日 動きなし・期日なし" });
  const rows = buildCleanupDecisions(
    [c("p"), c("q"), c("r"), c("s")],
    { p: { act: "close" }, q: { act: "drop" }, r: { act: "keep" }, s: { act: "reschedule", due: "2026-12-01" } },
    "n",
    "2026-11-27T11:00:00Z",
  );
  assert.deepEqual(rows.map((r) => r.action), ["close", "drop", "defer"]); // 日を変えるは 313 では記録しない
  for (const r of rows) {
    const p = r.payload as { origin?: string; label: string };
    assert.equal(p.origin, "313");
    assert.equal(p.label, "313週の整理");
    assert.ok(normalizeDecision(r).ok);
  }
  assert.equal(actLabel(c("p"), "drop"), "やめる");
  assert.equal(actLabel(card("z"), "drop"), "削除");
  assert.equal(groupOf(c("p")), "313");
  assert.equal(groupOf(card("z")), "star");
});

test("addDaysIso", () => assert.equal(addDaysIso("2026-11-17", 7), "2026-11-24"));
