/**
 * 315-B 停止・空回り（sync_meta.stall_watch_315b）の読み取り。壊れた記録は表示しない・異常を先に並べる。
 * Run: node --experimental-strip-types --test tests/stallWatch315b.test.mjs
 */
import assert from "node:assert/strict";
import test from "node:test";
import { ageText, isStallReportOld, parseStallReport, sortStallRows } from "../lib/stallWatch315b.ts";

const sample = {
  run_id: "315b-20261123-082000",
  checked_at: "2026-11-23T08:20:00+09:00",
  result: "partial",
  result_why: ["画面反映の失敗: x"],
  save: { ok: true },
  rows: [
    { id: "311", label: "311 送信前品質", status: "ok", why: "", last: null, age_h: 0.1, max_age_h: 1 },
    { id: "313", label: "313 完了候補確認", status: "idle", why: "同じ候補", last: null, age_h: 12, max_age_h: 26 },
    { id: "317", label: "317 コメント起動", status: "unknown", why: "ファイルなし", last: null, age_h: null, max_age_h: 2 },
    { id: "314", label: "314 業務品質監査", status: "stale", why: "古い", last: null, age_h: 300, max_age_h: 200 },
    { id: "999", label: "bad", status: "weird", why: "", last: null, age_h: null, max_age_h: null },
  ],
  pending: [],
};

test("parse accepts the Mac payload (string or object) and drops unknown statuses", () => {
  for (const raw of [sample, JSON.stringify(sample)]) {
    const r = parseStallReport(raw);
    assert.ok(r);
    assert.equal(r.result, "partial");
    assert.deepEqual(r.rows.map((x) => x.id), ["311", "313", "317", "314"]);
  }
});

test("broken records are not shown as normal", () => {
  assert.equal(parseStallReport(null), null);
  assert.equal(parseStallReport("{broken"), null);
  assert.equal(parseStallReport({ rows: "x", checked_at: "t" }), null);
  assert.equal(parseStallReport({ ...sample, result: "great" }).result, "partial");
});

test("abnormal rows come first (stale, unknown, idle, ok)", () => {
  const r = parseStallReport(sample);
  assert.deepEqual(sortStallRows(r.rows).map((x) => x.id), ["314", "317", "313", "311"]);
});

test("an old report is flagged and age text is short", () => {
  const t = Date.parse(sample.checked_at);
  assert.equal(isStallReportOld(sample, t + 10 * 3600_000), false);
  assert.equal(isStallReportOld(sample, t + 16 * 3600_000), true);
  assert.equal(isStallReportOld({ checked_at: "nope" }), true);
  assert.equal(ageText(0.5), "30分前");
  assert.equal(ageText(5), "5時間前");
  assert.equal(ageText(72), "3.0日前");
  assert.equal(ageText(null), "—");
});
