import assert from "node:assert/strict";
import test from "node:test";
import { judgeStarLabels } from "../lib/starLabels.ts";

const labels = [{ id: "Label_9", name: "Todoist済" }, { id: "Label_1", name: "仕事" }];

test("スター付きは starred", () => {
  assert.deepEqual(judgeStarLabels(["INBOX", "STARRED"], labels), { starred: true, todoistDone: false });
});

test("Todoist済ラベルは todoistDone", () => {
  assert.deepEqual(judgeStarLabels(["INBOX", "Label_9"], labels), { starred: false, todoistDone: true });
});

test("どちらも無ければ false・ラベルが無い箱でも落ちない", () => {
  assert.deepEqual(judgeStarLabels(["INBOX"], labels), { starred: false, todoistDone: false });
  assert.deepEqual(judgeStarLabels(["Label_9"], []), { starred: false, todoistDone: false });
  assert.deepEqual(judgeStarLabels(null, null), { starred: false, todoistDone: false });
});
