/**
 * FlowForge 直接編集（AIアシスタントを通さない）の依頼の点検。
 * Run: node --experimental-strip-types --test tests/flowforgePatchRequest.test.mjs
 */
import assert from "node:assert/strict";
import test from "node:test";

import { checkPatchRequest, PATCH_MAX_OPS } from "../lib/flowforgeEditView.ts";

const base = { agentId: "311", confirmedByUser: true };

test("patch request: accepts the three operations and normalizes them", () => {
  const r = checkPatchRequest({
    ...base,
    operations: [
      { op: "update_node", id: " n1 ", patch: { description: "説明" } },
      { op: "add_edge", source: "a", target: "b" },
      { op: "add_edge", source: "a", target: "c", replace: true },
      { op: "remove_edge", id: "e1" },
      { op: "remove_edge", source: "a", target: "b" },
    ],
  });
  assert.equal(r.ok, true);
  assert.deepEqual(r.operations[0], { op: "update_node", id: "n1", patch: { description: "説明" } });
  assert.deepEqual(r.operations[1], { op: "add_edge", source: "a", target: "b" });
  assert.equal(r.operations[2].replace, true);
});

test("patch request: needs confirmation, agent id and operations", () => {
  const ops = [{ op: "remove_edge", id: "e1" }];
  assert.equal(checkPatchRequest({ agentId: "311", operations: ops }).ok, false);
  assert.equal(checkPatchRequest({ agentId: "311", operations: ops, confirmedByUser: "yes" }).ok, false);
  assert.equal(checkPatchRequest({ ...base, agentId: "3", operations: ops }).ok, false);
  assert.equal(checkPatchRequest({ ...base, operations: [] }).ok, false);
  const many = Array.from({ length: PATCH_MAX_OPS + 1 }, () => ops[0]);
  assert.match(checkPatchRequest({ ...base, operations: many }).error, /too_many_operations/);
});

test("patch request: refuses fields and operations that could change structure", () => {
  const bad = [
    { op: "update_node", id: "n1", patch: { kind: "human" } },
    { op: "update_node", id: "n1", patch: { parentId: "x" } },
    { op: "update_node", id: "n1", patch: {} },
    { op: "update_node", id: "n1", patch: { title: "  " } },
    { op: "update_node", id: "n1", patch: { description: 3 } },
    { op: "update_node", patch: { title: "x" } },
    { op: "add_edge", source: "a" },
    { op: "add_edge", source: "a", target: "a" },
    { op: "remove_edge" },
    { op: "delete_node", id: "n1" },
    { op: "add_node", title: "x" },
    "update_node",
  ];
  for (const o of bad) {
    assert.equal(checkPatchRequest({ ...base, operations: [o] }).ok, false, JSON.stringify(o));
  }
});
