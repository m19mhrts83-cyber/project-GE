import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildDecisions,
  buildPlan,
  dayCounts,
  dayLabel,
  eventsByDay,
  initialState,
  threeWeeks,
  type Snapshot,
} from "../lib/weekPick.ts";
import { normalizeDecision } from "../lib/decisionContract.ts";

function snap(): Snapshot {
  const c = (id: string, extra: Partial<Snapshot["candidates"][number]> = {}) => ({
    kind: "task" as const, id, title: `仕事${id}`, mark: "none" as const, labels: [], priority: "p4", due: null, deadline: null,
    hard: false, left_from_last: false, weeks_carried: 0, score: 10, reasons: [{ tag: "small", text: "小さくてすぐ終わる" }],
    url: `https://app.todoist.com/app/task/${id}`, ...extra,
  });
  return {
    v: 1, rule_version: "rule-v1", generated_at: "2026-11-15T17:00:00+09:00", week: "2026-11-16",
    days: ["2026-11-16", "2026-11-18", "2026-11-20"], per_day: 3,
    last: { week: "2026-11-09", done: 3, done_titles: [], left: 1, added: 2, owner_open: 40 },
    candidates: [
      c("a", { left_from_last: true, due: "2026-11-13", weeks_carried: 1 }),
      c("b"), c("c", { due: "2026-11-19" }), c("d", { due: "2026-11-17", hard: true }), c("e", { due: "2026-11-12", left_from_last: true }),
    ],
    inlet: [{ kind: "inlet", id: "t1", title: "物件の件", body: "", source_ref: null, waited_days: 4, score: 14, reasons: [{ tag: "inlet", text: "入口で4日待っている" }] }],
    recommended: [{ id: "a", day: "2026-11-16" }, { id: "b", day: "2026-11-18" }],
    next_preview: ["c"],
    dated_in_week: [{ id: "c", title: "仕事c", date: "2026-11-19", hard: false }, { id: "d", title: "仕事d", date: "2026-11-17", hard: true }],
    hard_ahead: [],
  };
}

test("dayLabel と3週間", () => {
  assert.equal(dayLabel("2026-11-16"), "11/16(月)");
  assert.equal(dayLabel("2026-11-22"), "11/22(日)");
  const w = threeWeeks("2026-11-16");
  assert.equal(w.length, 3);
  assert.equal(w[2][6], "2026-12-06");
});

test("終日の複数日予定は各日に出る", () => {
  const by = eventsByDay({ generated_at: "", from: "", to: "", events: [
    { date: "2026-11-16", end_date: "2026-11-18", start: null, end: null, all_day: true, title: "旅行", kind: "family" },
  ] });
  assert.deepEqual(Object.keys(by).sort(), ["2026-11-16", "2026-11-17", "2026-11-18"]);
});

test("初期状態はAIの案どおり、残ったものは振り返りに", () => {
  const s = snap();
  const st = initialState(s);
  assert.equal(st.slots.a, "2026-11-16");
  assert.deepEqual(Object.keys(st.left).sort(), ["a", "e"]);
  assert.equal(st.reasons.b.text, "小さくてすぐ終わる");
  assert.equal(dayCounts(s, st)["2026-11-16"], 1);
});

test("plan: 置いたものに期日、選ばなかった今週の期日は外す（hard は残す）", () => {
  const s = snap();
  const st = initialState(s);
  st.slots.b = null; // AI 案を外す
  st.slots.c = "2026-11-20";
  st.left.e = { tags: ["too_big"], next: "drop", note: "もう要らない" };
  st.inlet.t1 = { action: "week", day: "2026-11-18" };
  const p = buildPlan(s, st);
  assert.deepEqual(p.set_due.map((x) => x.id).sort(), ["a", "c"]);
  assert.ok(!p.clear_due.includes("d"), "hard は外さない");
  assert.ok(p.clear_due.includes("e"), "やめるは期日を外す");
  assert.ok(p.notes.some((n) => n.id === "e" && n.text.includes("やめる") && n.text.includes("大きすぎ")));
  assert.equal(p.inlet[0].date, "2026-11-18");

  const rows = buildDecisions(s, st, p, "n1", "2026-11-15T20:00:00+09:00");
  const byKey = Object.fromEntries(rows.map((r) => [`${r.action}:${r.targetId}`, r]));
  assert.ok(byKey["pick:a"] && byKey["pick:c"] && byKey["defer:b"]);
  assert.ok(byKey["left:e"] && byKey["pick:t1"] && byKey["commit:2026-11-16"]);
  assert.equal(byKey["defer:b"].payload?.recommended, true);
  for (const r of rows) {
    const n = normalizeDecision(r);
    assert.ok(n.ok, `${r.action} ${r.targetId}: ${!n.ok ? n.error : ""}`);
  }
  const left = normalizeDecision(byKey["left:e"]);
  assert.ok(left.ok && (left.row.payload.reason_tags as string[]).includes("too_big"));
});
