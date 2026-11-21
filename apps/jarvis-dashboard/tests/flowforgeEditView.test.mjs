/**
 * FlowForge 編集用の読み取りと、待ち箱へ入れる前の点検。
 * Run: node --experimental-strip-types --test tests/flowforgeEditView.test.mjs
 */
import assert from "node:assert/strict";
import test from "node:test";

import {
  checkEditRequest,
  editViewFlowPayload,
  EDIT_INSTRUCTIONS_MAX_CHARS,
} from "../lib/flowforgeEditView.ts";

const payload = {
  flow: {
    id: "flow_x",
    name: "見本",
    updatedAt: "2026-11-21T00:00:00.000Z",
    nodes: [
      { id: "n1", position: { x: 1, y: 2 }, data: { kind: "start", title: "開始" } },
      { id: "g1", data: { kind: "subflow", title: "点検" } },
      { id: "n2", parentId: "g1", data: { kind: "claude", title: "照合", description: "宛先を照合する" } },
      { id: "n3", data: { kind: "tool", title: "経路B", toolName: "CLI" } },
      { id: "n4", data: { kind: "end", title: "完了" } },
    ],
    edges: [
      { id: "e1", source: "n1", target: "g1" },
      { id: "e2", source: "g1", target: "n4", label: "OK" },
    ],
  },
};

test("edit view keeps ids, descriptions, parents and edges, drops coordinates", () => {
  const v = editViewFlowPayload(payload);
  assert.equal(v.node_count, 5);
  assert.equal(v.edge_count, 2);
  assert.equal(v.updatedAt, "2026-11-21T00:00:00.000Z");
  const n2 = v.nodes.find((n) => n.id === "n2");
  assert.equal(n2.description, "宛先を照合する");
  assert.equal(n2.parentTitle, "点検");
  assert.ok(!("position" in v.nodes[0]));
  assert.deepEqual(v.edges[1], { id: "e2", from: "g1", to: "n4", fromTitle: "点検", toTitle: "完了", label: "OK" });
});

test("edit view lists unconnected top-level nodes only", () => {
  const v = editViewFlowPayload(payload);
  assert.deepEqual(v.unconnected, ["経路B"]);
});

test("edit view tolerates empty payload", () => {
  const v = editViewFlowPayload(null);
  assert.equal(v.node_count, 0);
  assert.deepEqual(v.edges, []);
});

test("queue request needs agent id, text and explicit user confirmation", () => {
  assert.equal(checkEditRequest({ agentId: "311", instructions: "a" }).ok, false);
  assert.equal(checkEditRequest({ agentId: "311", instructions: "a", confirmedByUser: "true" }).ok, false);
  assert.equal(checkEditRequest({ agentId: "31", instructions: "a", confirmedByUser: true }).ok, false);
  assert.equal(checkEditRequest({ agentId: "311", instructions: "  ", confirmedByUser: true }).ok, false);
  const ok = checkEditRequest({ agentId: "311", instructions: " 1. 経路Bを合流へつなぐ ", confirmedByUser: true });
  assert.deepEqual(ok, { ok: true, agentId: "311", instructions: "1. 経路Bを合流へつなぐ" });
});

test("queue request rejects long text and too many items", () => {
  const long = "あ".repeat(EDIT_INSTRUCTIONS_MAX_CHARS + 1);
  assert.equal(checkEditRequest({ agentId: "311", instructions: long, confirmedByUser: true }).ok, false);
  const many = Array.from({ length: 7 }, (_, i) => `${i + 1}. 変更${i + 1}`).join("\n");
  const r = checkEditRequest({ agentId: "311", instructions: many, confirmedByUser: true });
  assert.equal(r.ok, false);
  assert.match(r.error, /too_many_items/);
});
