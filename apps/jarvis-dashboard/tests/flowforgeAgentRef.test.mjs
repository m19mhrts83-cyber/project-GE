/**
 * agentId（315 / 315-B）→ フロー参照。書き込み先（queue・patch・status）の flowId 識別。
 * 本番へは何も書かない（待ち箱に入れる直前の flowId を、実データで確かめるだけ）。
 * Run: node --experimental-strip-types --test tests/flowforgeAgentRef.test.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { findFlowRef, findFlowRefByFlowId } from "../lib/flowforgeAgentRef.ts";
import { AGENT_ID_RE, checkEditRequest, checkPatchRequest } from "../lib/flowforgeEditView.ts";

const team = JSON.parse(readFileSync(new URL("../data/agentTeam.json", import.meta.url), "utf8"));
const shareCfg = JSON.parse(readFileSync(new URL("../../../config/flowforge_share_urls.json", import.meta.url), "utf8"));

const FLOW_A = "flow_S5g_i7CCiE0P6RKIp2_MkMTA";
const FLOW_B = "flow_qJcURKdC36ARzDdSwEfLisvt";
const SHARE_A = "2bg4-Vc8WOFzjEGe";
const SHARE_B = "oHjDFZowlMMaxtkb";

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
  assert.equal(findFlowRef(team.agents, "315-B").flowforge_id, FLOW_B);
});

test("write routes resolve the target via getFlowRefById (queue / patch / share)", () => {
  const read = (f) => readFileSync(new URL(`../lib/${f}`, import.meta.url), "utf8");
  const q = read("flowforgeEditQueue.ts");
  assert.equal((q.match(/getFlowRefById\(checked\.agentId\)/g) || []).length, 2);
  assert.ok(!q.includes("getAgentById"));
  assert.ok(read("flowforgeShareProxy.ts").includes("getFlowRefById(agentId)"));
});
