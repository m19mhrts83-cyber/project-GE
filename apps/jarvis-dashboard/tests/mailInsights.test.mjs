import assert from "node:assert/strict";
import test from "node:test";
import {
  bulkMinutes,
  closingLine,
  dailyBreakdown,
  hourly,
  insights,
  kpis,
  openingLine,
  peakHours,
  styleStats,
  weekKey,
  weeklyVolume,
} from "../lib/mailInsights.ts";

const d = (decided_at, action, over = {}) => ({ id: decided_at + action, decided_at, surface: "triage", action, ...over });

test("日別の内訳は JST の日で数え、知らない action は数えない", () => {
  const now = new Date("2026-11-17T12:00:00Z");
  const rows = [
    d("2026-11-16T16:30:00Z", "sent"), // JST 11/17 1:30
    d("2026-11-16T14:00:00Z", "skipped"), // JST 11/16 23:00
    d("2026-11-17T01:00:00Z", "comment"),
  ];
  const days = dailyBreakdown(rows, 2, now);
  assert.equal(days.length, 2);
  assert.deepEqual(days.map((x) => x.label), ["11/16", "11/17"]);
  assert.equal(days[0].skip, 1);
  assert.equal(days[1].sent, 1);
});

test("同じ1分に10件以上は一括として時間帯から外す", () => {
  const rows = [];
  for (let i = 0; i < 12; i++) rows.push(d(`2026-11-13T20:10:${String(i).padStart(2, "0")}Z`, "skipped"));
  rows.push(d("2026-11-13T13:00:00Z", "sent")); // JST 22時
  const bulk = bulkMinutes(rows);
  assert.equal(bulk.size, 1);
  const h = hourly(rows, bulk);
  assert.equal(h[22], 1);
  assert.equal(h[5], 0);
  assert.deepEqual(peakHours(h), [22]);
  const k = kpis(rows, 10, bulk);
  assert.equal(k.decided, 13);
  assert.equal(k.bulk, 12);
  assert.equal(k.skipped, 12);
  assert.equal(k.skippedWithReason, 0);
});

test("直しなし率は edited が分かる送信だけで数える", () => {
  const rows = [
    d("2026-11-10T00:00:00Z", "sent", { edited: false }),
    d("2026-11-10T01:00:00Z", "sent", { edited: true }),
    d("2026-11-10T02:00:00Z", "sent", { surface: "draft_review", edited: false }),
    d("2026-11-10T03:00:00Z", "good", { surface: "triage_miss" }),
    d("2026-11-10T04:00:00Z", "wrong", { surface: "triage_miss" }),
  ];
  const k = kpis(rows, 10, new Set());
  assert.equal(k.sent, 2);
  assert.equal(k.sentTotalForEdit, 3);
  assert.equal(k.sentUnedited, 2);
  assert.equal(k.missOk, 1);
  assert.equal(k.missTotal, 2);
});

test("週は JST の月曜で区切り、今週は含めない", () => {
  assert.equal(weekKey("2026-11-16T15:30:00Z"), "2026-11-16"); // JST 11/17(火) 0:30 → 月曜 11/16
  assert.equal(weekKey("2026-11-15T14:59:00Z"), "2026-11-09"); // JST 11/15(日) 23:59
  const now = new Date("2026-11-18T03:00:00Z");
  const w = weeklyVolume(
    [
      { created_at: "2026-11-10T03:00:00Z", lane: "partner" },
      { created_at: "2026-11-11T03:00:00Z", lane: "general" },
      { created_at: "2026-11-17T03:00:00Z", lane: "partner" },
    ],
    2,
    now,
  );
  assert.deepEqual(w.map((x) => x.key), ["2026-11-02", "2026-11-09"]);
  assert.equal(w[1].partner, 1);
  assert.equal(w[1].general, 1);
});

test("書き出しと結びは宛名・署名を外して拾う", () => {
  const t = "山村様\nご返信いただき、ありがとうございます。\n承知いたしました。\n今後ともよろしくお願いいたします。\n松野";
  assert.equal(openingLine(t), "ご返信いただき、ありがとうございます。");
  assert.equal(closingLine(t), "今後ともよろしくお願いいたします。");
  const s = styleStats([
    d("2026-11-10T00:00:00Z", "sent", { final_text: t }),
    d("2026-11-10T00:00:00Z", "sent", { final_text: "田中様\nご連絡ありがとうございます。\n今後ともよろしくお願いいたします。\n松野" }),
    d("2026-11-10T00:00:00Z", "skipped", { final_text: "x" }),
  ]);
  assert.equal(s.n, 2);
  assert.equal(s.closings[0].text, "今後ともよろしくお願いいたします。");
  assert.equal(s.closings[0].n, 2);
});

test("気づきは最大3件。理由なしの見送りが多いと先頭に出る", () => {
  const k = { decided: 30, bulk: 0, sent: 2, sentPerDay: 0.2, sentUnedited: 1, sentTotalForEdit: 2, missOk: 33, missTotal: 34, skipped: 20, skippedWithReason: 0, decideMsMedian: null };
  const weeks = [5, 6, 4, 18, 5].map((p, i) => ({ key: `k${i}`, label: `10/${i + 1}`, partner: p, general: 100 }));
  const out = insights({ k, weeks, peaks: [7, 22], totals: { partner: 250, general: 1600, since: "8/1" } });
  assert.equal(out.length, 3);
  assert.equal(out[0].title, "見送りの理由が残っていない");
  assert.match(out[1].title, /約14%/);
  assert.match(out[2].title, /10\/4の週/);
});
