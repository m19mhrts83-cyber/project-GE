import assert from "node:assert/strict";
import {
  buildQuietEdgeAsks,
  preferVitalByDay,
  formatHealthBitsForDay,
  treatmentYmdJst,
} from "../lib/quietEdgeContext";

function testPreferVital() {
  const m = preferVitalByDay([
    {
      recorded_at: "2026-08-07",
      metric: "spo2",
      value: 90,
      source: "health_unknown",
    },
    { recorded_at: "2026-08-07", metric: "spo2", value: 96, source: "oramemo" },
    {
      recorded_at: "2026-08-07",
      metric: "sleep_hours",
      value: 7.5,
      source: "watch",
    },
  ]);
  const day = m.get("2026-08-07");
  assert.equal(day?.get("spo2"), 96);
  assert.equal(day?.get("sleep_hours"), 7.5);
  assert.equal(formatHealthBitsForDay(day), "睡眠7.5h / SpO2 96%");
}

function testHealthGapAsk() {
  const asks = buildQuietEdgeAsks({
    journals: [
      {
        recorded_at: "2026-08-06",
        excerpt: "夜の防衛線 23:30 達成（〇） よく眠れたメモ".repeat(2),
        char_count: 120,
        source: "test",
        sleep_signal: "夜の防衛線 23:30 達成（〇）",
        sleep_tags: ["defense_line", "bedtime_ok"],
      },
    ],
    notes: [],
    snore: [{ recorded_at: "2026-08-06", score: 22, count: 100 }],
    vitals: [],
    windowDays: 14,
    maxAsks: 5,
  });
  assert.ok(
    asks.some((a) => a.trigger === "health_gap" && a.recorded_at === "2026-08-06"),
    `expected health_gap ask, got ${asks.map((a) => a.trigger).join(",")}`,
  );
}

function testTreatmentYmd() {
  assert.equal(treatmentYmdJst("2026-08-07T15:00:00+09:00"), "2026-08-07");
}

testPreferVital();
testHealthGapAsk();
testTreatmentYmd();
console.log("quietEdgeContext smoke ok");
