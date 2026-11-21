/**
 * agentId（315 / 315-B）→ フロー参照。書き込み先（queue・patch・status）の flowId 識別。
 * 本番へは何も書かない（待ち箱に入れる直前の flowId を、実データで確かめるだけ）。
 * Run: node --experimental-strip-types --test tests/flowforgeAgentRef.test.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import ts from "typescript";
import * as editView from "../lib/flowforgeEditView.ts";

import { findFlowRef, findFlowRefByFlowId } from "../lib/flowforgeAgentRef.ts";
import { AGENT_ID_RE, checkEditRequest, checkPatchRequest } from "../lib/flowforgeEditView.ts";

const team = JSON.parse(readFileSync(new URL("../data/agentTeam.json", import.meta.url), "utf8"));
const shareCfg = JSON.parse(readFileSync(new URL("../../../config/flowforge_share_urls.json", import.meta.url), "utf8"));

const FLOW_A = "flow_S5g_i7CCiE0P6RKIp2_MkMTA";
const FLOW_B = "flow_ZQIfYZY4GJF2XspXY8i0sGWD";
const OLD_FLOW_B = "flow_qJcURKdC36ARzDdSwEfLisvt";
const OLD_SHARE_B = "oHjDFZowlMMaxtkb";
const SHARE_A = "2bg4-Vc8WOFzjEGe";
const SHARE_B = "smnVr23mbD8pb2sT";

test("315 is 315-A and 315-B is 315-B (never swapped)", () => {
  assert.equal(findFlowRef(team.agents, "315").flowforge_id, FLOW_A);
  assert.equal(findFlowRef(team.agents, "315-B").flowforge_id, FLOW_B);
  assert.ok(findFlowRef(team.agents, "315").flowforge_share_url.endsWith(`/share/${SHARE_A}`));
  assert.ok(findFlowRef(team.agents, "315-B").flowforge_share_url.endsWith(`/share/${SHARE_B}`));
});

test("reverse lookup by flowId keeps both flows apart", () => {
  assert.equal(findFlowRefByFlowId(team.agents, FLOW_A).agentId, "315");
  assert.equal(findFlowRefByFlowId(team.agents, FLOW_B).agentId, "315-B");
  assert.equal(findFlowRefByFlowId(team.agents, "flow_nope"), undefined);
});

test("unregistered ids stay unresolved (same error path as before)", () => {
  assert.equal(findFlowRef(team.agents, "315-C"), undefined);
  assert.equal(findFlowRef(team.agents, "999"), undefined);
  assert.equal(findFlowRef(team.agents, "315-b"), undefined);
});

test("other agents are unchanged: every agent resolves to its own flow", () => {
  for (const a of team.agents) {
    if (!a.flowforge_id) continue;
    assert.equal(findFlowRef(team.agents, a.id).flowforge_id, a.flowforge_id, a.id);
  }
  assert.equal(findFlowRef(team.agents, "316").flowforge_id, "flow_TA9fHAyKHFlfTFb8fvpDG6Nh");
});

test("the 315 row is still 315 (not replaced by 315-B)", () => {
  const row = team.agents.find((a) => a.id === "315");
  assert.equal(row.flowforge_id, FLOW_A);
  assert.equal(team.agents.filter((a) => a.id.startsWith("315")).length, 1);
});

test("share config and registry agree for 315 / 315-B", () => {
  assert.ok(shareCfg.by_agent_id["315"].endsWith(SHARE_A));
  assert.ok(shareCfg.by_agent_id["315-B"].endsWith(SHARE_B));
  assert.ok(shareCfg.by_flow_id[FLOW_B].endsWith(SHARE_B));
  assert.ok(shareCfg.by_flow_id[OLD_FLOW_B].endsWith(OLD_SHARE_B));
  assert.equal(findFlowRefByFlowId(team.agents, OLD_FLOW_B), undefined);
});

test("agentId format: 3 digits, or 3 digits + -capital letter", () => {
  for (const ok of ["311", "315", "315-B"]) assert.ok(AGENT_ID_RE.test(ok), ok);
  for (const bad of ["31", "3155", "315-", "315-b", "315-BB", "abc", "315 B", "315-B\n"]) {
    assert.ok(!AGENT_ID_RE.test(bad), JSON.stringify(bad));
  }
});

test("MCP input check: edit and patch requests accept 315-B and keep the agentId", () => {
  const e = checkEditRequest({ agentId: "315-B", instructions: "1. 説明文を直す", confirmedByUser: true });
  assert.equal(e.ok, true);
  assert.equal(e.agentId, "315-B");
  assert.equal(checkEditRequest({ agentId: "315-b", instructions: "1. x", confirmedByUser: true }).ok, false);
  const p = checkPatchRequest({
    agentId: "315-B",
    operations: [{ op: "update_node", id: "n1", patch: { description: "x" } }],
    confirmedByUser: true,
  });
  assert.equal(p.ok, true);
  assert.equal(p.agentId, "315-B");
  // 書き込み先 flowId は検査済みの agentId から決まる
  assert.equal(findFlowRef(team.agents, p.agentId).flowforge_id, FLOW_B);
});

test("write routes resolve the target via getFlowRefById (queue / patch / share)", () => {
  const read = (f) => readFileSync(new URL(`../lib/${f}`, import.meta.url), "utf8");
  const q = read("flowforgeEditQueue.ts");
  assert.equal((q.match(/getFlowRefById\(checked\.agentId\)/g) || []).length, 2);
  assert.ok(!q.includes("getAgentById"));
  assert.ok(read("flowforgeShareProxy.ts").includes("getFlowRefById(agentId)"));
});

// Execute the actual queue function with an in-memory Supabase boundary.
// No network or production writes; inspect the payload that would be inserted.
test("patch queue inserts the rebuilt 315-B flowId and preserves 315-A", async () => {
  const source = readFileSync(new URL("../lib/flowforgeEditQueue.ts", import.meta.url), "utf8");
  const js = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  let inserted;
  const sb = { from() { return {
    select() { return { in: async () => ({ count: 0 }) }; },
    insert(row) { inserted = row; return { select() { return { single: async () => ({ data: row }) }; } }; },
  }; } };
  const exports = {};
  const dependencies = {
    "@/lib/agentTeam": { getFlowRefById: (id) => findFlowRef(team.agents, id) },
    "@/lib/supabase/admin": { createServiceClient: () => sb },
    "@/lib/flowforgeEditView": editView,
  };
  new Function("require", "exports", js)((id) => {
    assert.ok(Object.hasOwn(dependencies, id), `unexpected dependency: ${id}`);
    return dependencies[id];
  }, exports);
  for (const [agentId, flowId] of [["315-B", FLOW_B], ["315", FLOW_A]]) {
    const result = await exports.queueFlowforgePatch({
      agentId, confirmedByUser: true,
      operations: [{ op: "update_node", id: "n1", patch: { description: "test only" } }],
    });
    assert.equal(result.ok, true);
    assert.equal(inserted.agent_id, agentId);
    assert.equal(inserted.flow_id, flowId);
    assert.equal(inserted.kind, "patch");
  }
});

test('714 resolves only to the UI-owned verified flow, never the local-only draft', () => {
  const ref=findFlowRef(team.agents,'714');
  assert.equal(ref.flowforge_id,'flow_q41qaFFwQ_pX4m6qg04oLb3H');
  assert.ok(ref.flowforge_share_url.endsWith('/share/HI4KOYwORPb7ZG1d'));
  assert.equal(shareCfg.by_agent_id['714'],ref.flowforge_share_url);
  assert.equal(shareCfg.by_flow_id[ref.flowforge_id],ref.flowforge_share_url);
  assert.equal(findFlowRefByFlowId(team.agents,'flow_714minutes_20261122'),undefined);
  assert.equal(team.agents.filter(a=>a.id==='714').length,1);
});
