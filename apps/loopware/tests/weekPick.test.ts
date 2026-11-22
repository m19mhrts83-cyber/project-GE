import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildDecisions,
  buildPlan,
  dayCounts,
  dayLabel,
  deepOf,
  deepOver,
  deepTitle,
  deferredReason,
  eventsByDay,
  initialState,
  placedTotal,
  placedWeights,
  regularCap,
  threeWeeks,
  weightLabel,
  weightOf,
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


test("判断の重さ: 置いた件の内訳・じっくりの上限超え・翌週へ回した理由", () => {
  const s = snap();
  s.candidates[0].weight = "quick";
  s.candidates[1].weight = "deep";
  s.candidates[2].weight = "deep";
  s.weight = {
    ok: true, error: "", decision_id: "D-20261123-weekly-weight-ab",
    labels: { quick: "すぐ決まる", deep: "じっくり", unknown: "未判別" }, deep_per_week: 1,
    recommended: { quick: 1, deep: 1, unknown: 0 }, candidates: { quick: 1, deep: 2, unknown: 2 },
    deferred: [{ id: "c", reason: "じっくりは週1件まで。翌週以降の候補へ" }],
  };
  const st = initialState(s);
  assert.deepEqual(placedWeights(s, st), { quick: 1, deep: 1, unknown: 0 });
  assert.equal(deepOver(s, st), 0);
  // 本人が2件目のじっくりを足しても上書きしない（知らせるだけ）
  st.slots.c = "2026-11-20";
  assert.equal(st.slots.c, "2026-11-20");
  assert.equal(deepOver(s, st), 1);
  assert.equal(deferredReason(s, "c"), "じっくりは週1件まで。翌週以降の候補へ");
  assert.equal(deferredReason(s, "a"), null);
  assert.equal(weightLabel(s, "deep"), "じっくり");
  const rows = buildDecisions(s, st, buildPlan(s, st), "n1", "2026-11-15T12:00:00Z");
  const pickA = rows.find((r) => r.targetId === "a" && r.action === "pick");
  assert.equal((pickA?.payload as { weight?: string }).weight, "quick");
  const commit = rows.find((r) => r.action === "commit");
  assert.deepEqual((commit?.payload as { weights?: unknown }).weights, { quick: 1, deep: 2, unknown: 0 });
});

test("判断の重さ: 古い snapshot（weight なし）は未判別・上限なし", () => {
  const s = snap();
  const st = initialState(s);
  assert.equal(weightOf(s.candidates[0]), "unknown");
  assert.deepEqual(placedWeights(s, st), { quick: 0, deep: 0, unknown: 2 });
  assert.equal(deepOver(s, st), 0);
});


function deepSnap(staff: boolean) {
  const s = snap();
  s.candidates[1].weight = "deep";
  s.candidates[1].weight_why = "検討・設計・方針などの語";
  s.recommended = [{ id: "a", day: "2026-11-16" }];
  s.weight = {
    ok: true, error: "", decision_id: "D-x", labels: { quick: "すぐ決まる", deep: "じっくり", unknown: "未判別" }, deep_per_week: 1,
    recommended: { quick: 0, deep: 1, unknown: 1 }, candidates: { quick: 0, deep: 1, unknown: 4 }, deferred: [],
  };
  s.deep_frame = {
    days: ["2026-11-17", "2026-11-20"], recommended: staff ? null : "b", staff_label: "社員のフロー磨き込み",
    staff_steps: ["チャッピー相談", "図で確認", "本人判断", "運用で確認"],
    staff: staff ? { staff: "社員X", decision_id: "D-staff", title: "社員X: 作業フローの磨き込み（チャッピー相談→図で確認→本人判断→運用で確認）" } : null,
  };
  return s;
}

test("じっくり枠: タスクは火に期日・金はコメント、9件に2回分を数える", () => {
  const s = deepSnap(false);
  const st = initialState(s);
  assert.deepEqual(deepOf(s, st), { kind: "task", id: "b" });
  assert.equal(regularCap(s), 7);
  assert.equal(placedTotal(s, st), 3); // 月1件＋枠2回
  assert.deepEqual(placedWeights(s, st), { quick: 0, deep: 1, unknown: 1 });
  const plan = buildPlan(s, st);
  assert.ok(plan.set_due.some((x) => x.id === "b" && x.date === "2026-11-17"));
  assert.ok(plan.notes.some((n) => n.id === "b" && n.text.includes("2回目 11/20(金)")));
  assert.deepEqual(plan.deep_frame, { kind: "task", id: "b", days: ["2026-11-17", "2026-11-20"] });
  const rows = buildDecisions(s, st, plan, "n1", "2026-11-15T12:00:00Z");
  const d = rows.find((r) => r.idemKey?.includes(":deep:b"));
  assert.equal(d?.action, "pick");
  assert.equal((d?.payload as { deep_frame?: boolean }).deep_frame, true);
});

test("じっくり枠: 本人が決めた社員は Todoist に起票しない（判断ログだけ）", () => {
  const s = deepSnap(true);
  const st = initialState(s);
  const d = deepOf(s, st);
  assert.deepEqual(d, { kind: "staff", name: "社員X", decision_id: "D-staff" });
  assert.ok(deepTitle(s, d).startsWith("社員X: 作業フローの磨き込み"));
  const plan = buildPlan(s, st);
  assert.equal(plan.set_due.length, 1); // 月の a だけ。社員の分は期日を入れない
  assert.deepEqual(plan.inlet, []);
  assert.equal(plan.deep_frame?.kind, "staff");
  const rows = buildDecisions(s, st, plan, "n1", "2026-11-15T12:00:00Z");
  const row = rows.find((r) => r.targetType === "weekly_deep_frame");
  assert.equal(row?.action, "pick");
  assert.equal((row?.payload as { staff?: string }).staff, "社員X");
  assert.equal((row?.payload as { kept_ai?: boolean }).kept_ai, true);
});

test("じっくり枠: 本人が空けたら上書きしない・古い下書き（deep なし）は案のまま", () => {
  const s = deepSnap(false);
  const st = initialState(s);
  st.deep = { kind: "none" };
  assert.deepEqual(deepOf(s, st), { kind: "none" });
  assert.equal(placedTotal(s, st), 1);
  assert.equal(buildPlan(s, st).deep_frame, null);
  const old = initialState(s);
  delete old.deep;
  assert.deepEqual(deepOf(s, old), { kind: "task", id: "b" });
});
