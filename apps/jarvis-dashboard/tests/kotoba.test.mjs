import assert from "node:assert/strict";
import test from "node:test";
import { SHELVES, VERDICT, filterByStatus, groupByShelf, isCardId, isShelf, whoWhere } from "../lib/kotoba.ts";

const card = (over) => ({
  id: "00000000-0000-4000-8000-000000000001",
  body: "データから導き出すルールは仮説",
  speaker: "池田さん",
  speaker_guess: false,
  where_label: "ループウェアDay2",
  occurred_on: "2026-11-08",
  at_label: "約8分",
  source: "genspark",
  source_ref: {},
  background: null,
  kind: "criterion",
  shelves: ["AI・仕組みづくり"],
  is_summary: false,
  status: "candidate",
  created_at: "2026-11-11T00:00:00Z",
  ...over,
});

test("判断はカードの状態と契約の action に写る（迷うはNGに混ぜない）", () => {
  assert.deepEqual(VERDICT.keep, { status: "kept", action: "accept" });
  assert.deepEqual(VERDICT.drop, { status: "dropped", action: "reject" });
  assert.deepEqual(VERDICT.hesitate, { status: "hesitated", action: "hesitated" });
  assert.equal(VERDICT.comment.status, null);
});

test("誰が／どこで: 推定と不明を区別し、日付は月/日", () => {
  assert.equal(whoWhere(card({})), "池田さん／11/8 ループウェアDay2 約8分");
  assert.equal(whoWhere(card({ speaker: "松野", speaker_guess: true, at_label: null })), "松野（推定）／11/8 ループウェアDay2");
  assert.equal(whoWhere(card({ speaker: null, where_label: null, occurred_on: null, at_label: null })), "話者不明");
});

test("棚ごとに並べる: 複数の棚に入り、棚なしは未分類で最後", () => {
  const a = card({ id: "a", shelves: ["家族", "働き方・心の持ち方"] });
  const b = card({ id: "b", shelves: [], status: "kept" });
  const c = card({ id: "c", shelves: ["家族"], status: "hesitated" });
  const g = groupByShelf([a, b, c]);
  assert.deepEqual(
    g.map((x) => x.shelf),
    ["働き方・心の持ち方", "家族", "未分類"],
  );
  const fam = g.find((x) => x.shelf === "家族");
  assert.equal(fam.cards.length, 2);
  assert.equal(fam.counts.candidate, 1);
  assert.equal(fam.counts.hesitated, 1);
});

test("絞り込み: 既定は「いらない」以外、all は全部", () => {
  const list = [card({ id: "1", status: "dropped" }), card({ id: "2", status: "kept" }), card({ id: "3" })];
  assert.equal(filterByStatus(list, undefined).length, 2);
  assert.equal(filterByStatus(list, "all").length, 3);
  assert.equal(filterByStatus(list, "kept").length, 1);
  assert.equal(filterByStatus(list, "bogus").length, 2);
});

test("入力の検査", () => {
  assert.equal(isCardId("00000000-0000-4000-8000-000000000001"), true);
  assert.equal(isCardId("x"), false);
  assert.equal(isShelf(SHELVES[0]), true);
  assert.equal(isShelf("未分類"), false);
});
