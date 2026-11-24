import { test } from "node:test";
import assert from "node:assert/strict";
import {
  LATER,
  adoptSuggestions,
  applyFilter,
  cleanupChoice,
  cleanupItem,
  countBy,
  mailItem,
  ruleItem,
  sortItems,
  topicItem,
  weekItem,
  weightMap,
  zaimItem,
} from "../lib/allCore.ts";

// すべてダミー（実在の相手・金額は入れない）
const mail = (o: Record<string, unknown>) =>
  mailItem({ id: "m1", subject: "件名", who: "相手", lane: "general", postedToSlack: false, hesitatedAt: null, score: null, receivedAt: null, summary: "", ...o } as never);
const clean = (o: Record<string, unknown>, weights?: ReturnType<typeof weightMap>) =>
  cleanupItem({ id: "c1", title: "t", sender: "s", summary: "", suggest: "keep", why: "w", age_days: 10, deadline: null, due: null, priority: 1, gmail_url: "", ...o } as never, "2026-11-24", weights);

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
  assert.equal(clean({ suggest: "keep" }).suggest, LATER);
});

test("片付けは出どころでジャンルが分かれる（318／313／スター）", () => {
  assert.equal(clean({ origin: "318" }).genre, "g318");
  assert.equal(clean({ origin: "313" }).genre, "g313");
  assert.equal(clean({}).genre, "star");
  assert.equal(clean({ origin: "318" }).level, 2);
});

test("313 は 済み／やめる／残す。318・スターに『削除』は出さず、削除のおすすめは提案にしない", () => {
  const w313 = clean({ origin: "313", suggest: "drop" });
  assert.deepEqual(w313.options.map((o) => o.label), ["済み", "やめる", "残す"]);
  assert.equal(w313.suggest, "drop");
  const star = clean({ suggest: "drop" });
  assert.deepEqual(star.options.map((o) => o.act), ["close", LATER]);
  assert.equal(star.suggest, null);
  assert.match(star.why, /削除はここでは選べない/);
});

test("片付けの選択は既存の処置だけに写す（313 以外の drop は送らない）", () => {
  assert.deepEqual(cleanupChoice(clean({ origin: "313" }), "drop"), { act: "drop" });
  assert.equal(cleanupChoice(clean({}), "drop"), null);
  assert.equal(cleanupChoice(clean({ origin: "318" }), "drop"), null);
  assert.deepEqual(cleanupChoice(clean({}), LATER), { act: "keep" });
  assert.deepEqual(cleanupChoice(clean({}), "close"), { act: "close" });
  assert.equal(cleanupChoice(mail({}), "close"), null);
});

test("期日超過の日数と、今週の9件の材料から判断の重さが付く", () => {
  assert.equal(clean({ deadline: "2026-11-20" }).overdue, 4);
  assert.equal(clean({ due: "2026-11-21" }).overdue, 3);
  assert.equal(clean({}).overdue, null);
  const wm = weightMap({ candidates: [{ id: "c1", weight: "quick", weight_why: "返事だけ" }, { id: "c2", weight: "unknown" }] } as never);
  assert.equal(clean({}, wm).weight, "quick");
  assert.equal(clean({}, wm).weightWhy, "返事だけ");
  assert.equal(clean({ id: "c2" }, wm).weight, undefined);
});

test("お題は推しの案が提案になる。無ければ提案なし", () => {
  const t = { id: "t1", title: "x", topicText: "[Slack] 起票して", proposals: [{ index: 1, label: "追記", body: "" }, { index: 2, label: "別", body: "" }] };
  assert.equal(topicItem({ ...t, starred: 2 } as never).suggest, "pick:2");
  assert.equal(topicItem(t as never).suggest, null);
});

test("今週の9件は未確定の週だけ1行。その場のボタンは無く /week へ開く", () => {
  const snap = { week: "2026-11-30", candidates: [{ id: "a", weight: "quick" }, { id: "b", weight: "deep" }, { id: "c" }], inlet: [] } as never;
  const it = weekItem(snap, false, "2026-11-28")!;
  assert.equal(it.genre, "week");
  assert.equal(it.options.length, 0);
  assert.equal(it.link, "/week");
  assert.equal(it.level, 3);
  assert.match(it.summary, /すぐ決まる 1／じっくり 1／未判別 1/);
  assert.equal(weekItem(snap, true, "2026-11-28"), null);
  assert.equal(weekItem(null, false, "2026-11-28"), null);
  assert.equal(weekItem(snap, false, "2026-11-24")!.level, 2);
});

test("Zaim は 正しい／違う、ルール候補は 採用／今回だけ／違う。どちらも提案は置かない", () => {
  const z = zaimItem({ id: "z1", proposal: "費目A→費目B", shop: "店", amount: null, status: "pending_confirm", at: null });
  assert.deepEqual(z.options.map((o) => o.act), ["good", "wrong"]);
  assert.equal(z.suggest, null);
  const r = ruleItem({ id: "C0123abcd", kind: "hide", employee: "317", key: "k", rule_line: "線", text: "本文", why: "根拠", evidence: [1, 2], status: "candidate" });
  assert.deepEqual(r.options.map((o) => o.act), ["accept", "once", "reject"]);
  assert.equal(r.suggest, null);
  assert.equal(r.genre, "rule");
});

test("重要度の高い順に並べ、絞り込みと件数が合う", () => {
  const items = sortItems([mail({ id: "a" }), mail({ id: "b", lane: "partner" }), clean({ id: "z", suggest: "close" })]);
  assert.equal(items[0].id, "b");
  assert.equal(applyFilter(items, { genre: "star", level: 0 }).length, 1);
  assert.equal(applyFilter(items, { genre: "all", level: 3 }).length, 1);
  assert.equal(applyFilter(items, { genre: "all", level: 0, suggestOnly: true }).length, 1);
  const n = countBy(items);
  assert.equal(n.total, 3);
  assert.equal(n.level[3], 1);
  assert.equal(n.genre.star, 1);
  assert.equal(n.suggest, 1);
});

test("期日超過順は超過の多い順、すぐ決まる順は quick が先・開いて決める行は後ろ", () => {
  const wm = weightMap({ candidates: [{ id: "q", weight: "quick" }, { id: "d", weight: "deep" }] } as never);
  const a = clean({ id: "o1", deadline: "2026-11-10" });
  const b = clean({ id: "o2", deadline: "2026-11-20" });
  const c = mail({ id: "m" });
  assert.deepEqual(sortItems([c, b, a], "overdue").map((i) => i.id), ["o1", "o2", "m"]);
  const wk = weekItem({ week: "2026-11-30", candidates: [], inlet: [] } as never, false, "2026-11-28")!;
  const q = sortItems([wk, clean({ id: "d" }, wm), mail({ id: "m" }), clean({ id: "q" }, wm)], "quick").map((i) => i.id);
  assert.equal(q[0], "q");
  assert.equal(q[q.length - 1], "2026-11-30");
  assert.ok(q.indexOf("d") > q.indexOf("m"));
});

test("提案どおりは未選択の行にだけ入り、選び直しを上書きしない。only でチェックした行だけ", () => {
  const items = [clean({ id: "a", suggest: "close" }), clean({ id: "b", suggest: "keep" }), mail({ id: "m" })];
  const r = adoptSuggestions(items, { "cleanup:b": "close" });
  assert.deepEqual(r, { "cleanup:a": "close", "cleanup:b": "close" });
  const only = adoptSuggestions(items, {}, new Set(["cleanup:b"]));
  assert.deepEqual(only, { "cleanup:b": LATER });
});
