import { test } from "node:test";
import assert from "node:assert/strict";
import { buildCleanupDecisions, addDaysIso, type CleanupCard } from "../lib/cleanupBulk.ts";
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

test("addDaysIso", () => assert.equal(addDaysIso("2026-11-17", 7), "2026-11-24"));
