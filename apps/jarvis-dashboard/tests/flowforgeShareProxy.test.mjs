/**
 * Pure-ish checks for FlowForge proxy helpers (no Next server).
 * Run: node --test apps/jarvis-dashboard/tests/flowforgeShareProxy.test.mjs
 *
 * Note: TS lib is exercised via duplicated extract regex here for CI-light check.
 * Full route test: local next + curl (see docs 54b).
 */
import assert from "node:assert/strict";
import test from "node:test";

const SHARE_ID_RE = /\/share\/([A-Za-z0-9_-]+)/;
const FLOW_ID_RE = /\/flows\/(flow_[A-Za-z0-9_-]+)/;

function extractShareId(input) {
  const t = input.trim();
  const m = SHARE_ID_RE.exec(t);
  if (m) return m[1];
  if (/^[A-Za-z0-9_-]{8,64}$/.test(t) && !t.startsWith("flow_")) return t;
  return null;
}

function extractFlowId(input) {
  const t = input.trim();
  const m = FLOW_ID_RE.exec(t);
  if (m) return m[1];
  if (/^flow_[A-Za-z0-9_-]+$/.test(t)) return t;
  return null;
}

test("extractShareId from URL and bare id", () => {
  assert.equal(
    extractShareId(
      "https://flowforge-259747770348.asia-northeast1.run.app/share/tn9-F4fhdIgHVpRl",
    ),
    "tn9-F4fhdIgHVpRl",
  );
  assert.equal(extractShareId("tn9-F4fhdIgHVpRl"), "tn9-F4fhdIgHVpRl");
});

test("extractFlowId from URL and bare id", () => {
  assert.equal(
    extractFlowId(
      "https://flowforge-259747770348.asia-northeast1.run.app/flows/flow_M8SvKC1IDTDi496Vw-DgGjpD",
    ),
    "flow_M8SvKC1IDTDi496Vw-DgGjpD",
  );
  assert.equal(
    extractFlowId("flow_M8SvKC1IDTDi496Vw-DgGjpD"),
    "flow_M8SvKC1IDTDi496Vw-DgGjpD",
  );
});

test("upstream share fetch with Origin (live)", async () => {
  const base = "https://flowforge-259747770348.asia-northeast1.run.app";
  const shareId = "tn9-F4fhdIgHVpRl";
  const res = await fetch(`${base}/api/shares/${shareId}`, {
    headers: {
      Accept: "application/json",
      Origin: base,
      Referer: `${base}/share/${shareId}`,
    },
  });
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.flow?.id, "flow_M8SvKC1IDTDi496Vw-DgGjpD");
  assert.ok(Array.isArray(body.flow?.nodes));
  assert.ok(body.flow.nodes.length >= 1);
});
