/**
 * MCP JSON-RPC shape checks (no Next server).
 * Run: node --test apps/jarvis-dashboard/tests/flowforgeMcp.test.mjs
 */
import assert from "node:assert/strict";
import test from "node:test";

test("tools/list style payload has resolve_flowforge_flow", () => {
  const tools = [
    {
      name: "resolve_flowforge_flow",
      description: "read-only",
      inputSchema: { type: "object", properties: { url: { type: "string" } } },
    },
  ];
  assert.equal(tools[0].name, "resolve_flowforge_flow");
  assert.ok(tools[0].inputSchema.properties.url);
});

test("initialize result shape", () => {
  const result = {
    protocolVersion: "2024-11-05",
    capabilities: { tools: {} },
    serverInfo: { name: "jarvis-flowforge-read", version: "1.0.0" },
  };
  assert.equal(result.serverInfo.name, "jarvis-flowforge-read");
});
