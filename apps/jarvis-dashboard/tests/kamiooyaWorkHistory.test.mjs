import test from "node:test";
import assert from "node:assert/strict";
import { workTotals, parseWorkHistory } from "../lib/kamiooyaWorkHistory.ts";

test("confirmed correction replaces estimated time without counting agent time as owner work", () => {
  const event = { id: "old", item_id: "a", at: "2026-11-01T12:00:00+09:00", actor: "Chappy", summary: "記録", kind: "log", minutes: 30, time_kind: "estimated", evidence: [] };
  const events = [event, { ...event, id: "confirmed", time_kind: "owner_confirmed", minutes: 20, supersedes: "old" }, { ...event, id: "agent", time_kind: "agent_elapsed", minutes: 60 }, { ...event, id: "unknown", time_kind: "unrecorded", minutes: null }];
  assert.deepEqual(workTotals(events), { confirmed: 20, estimated: 0, agent: 60, unrecorded: 1 });
});

test("missing history and malformed history are distinguishable", () => {
  assert.equal(parseWorkHistory(null), null);
  assert.throws(() => parseWorkHistory('{"version":1,"projects":[{"id":"p"}]}'));
});
