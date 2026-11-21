/**
 * FlowForge 書き込み中核（flowforgeWrite.ts）のモックテスト。実通信なし。
 * Run: node --experimental-strip-types --test tests/flowforgeWrite.test.mjs
 */
import assert from "node:assert/strict";
import test from "node:test";
import {
  applyChange,
  applyChanges,
  contentHash,
  parseAllowList,
  previewChange,
  rollbackFlow,
  WriteError,
} from "../lib/flowforgeWrite.ts";

const FID = "flow_TESTonly_1";
const baseFlow = () => ({
  id: FID,
  name: "テスト",
  description: "d",
  createdAt: "2026-01-01T00:00:00.000Z",
  updatedAt: "2026-01-02T00:00:00.000Z",
  look: { v: 1 },
  nodes: [
    { id: "start", data: { kind: "start", title: "開始", label: "開始", description: "s" }, position: { x: 0, y: 0 } },
    { id: "a", data: { kind: "tool", title: "A", description: "da" }, position: { x: 1, y: 0 } },
    { id: "b", data: { kind: "human", title: "B", description: "db" }, position: { x: 2, y: 0 } },
    { id: "end", data: { kind: "end", title: "終了" }, position: { x: 3, y: 0 } },
  ],
  edges: [
    { id: "e1", source: "start", target: "a" },
    { id: "e2", source: "a", target: "end" },
  ],
});

const env = (o = {}) => ({ allowedFlowIds: [FID], anonIdSet: true, signingKey: "k", ...o });

function mkDeps(initial = baseFlow(), opts = {}) {
  const state = { flow: initial, synced: [], backups: [], syncCalls: 0 };
  const deps = {
    fetchFlow: async () => JSON.parse(JSON.stringify(state.flow)),
    syncFlow: async (f) => {
      state.syncCalls++;
      if (opts.syncThrows) throw new Error("boom");
      state.synced.push(f);
      if (!opts.snapshot) state.flow = JSON.parse(JSON.stringify(f));
    },
    saveBackup: async (id, f) => {
      if (opts.backupThrows) throw new Error("ro fs");
      state.backups.push(f);
      return { id: `${id}__x.json`, durable: true };
    },
    now: () => new Date("2026-02-03T04:05:06.000Z"),
  };
  return { state, deps };
}

const changes = {
  nodes: [{ id: "a", title: "A改", description: "da2" }],
  addEdges: [{ source: "a", target: "b" }, { source: "b", target: "end" }],
  removeEdges: [{ id: "e2" }],
};

async function rejects(p, status, code) {
  await assert.rejects(p, (e) => {
    assert.ok(e instanceof WriteError, String(e));
    assert.equal(e.status, status, `${e.code}`);
    assert.equal(e.code, code);
    return true;
  });
}

test("allowlist parse: 空は空、不正な値は捨てる", () => {
  assert.deepEqual(parseAllowList(""), []);
  assert.deepEqual(parseAllowList(undefined), []);
  assert.deepEqual(parseAllowList("flow_a, bad ,flow_b-c"), ["flow_a", "flow_b-c"]);
});

test("applyChanges: 差分が出て、元は変更されない", () => {
  const base = baseFlow();
  const { next, diff } = applyChanges(base, changes);
  assert.deepEqual(base, baseFlow());
  assert.equal(next.nodes[1].data.title, "A改");
  assert.equal(next.nodes[0].data.kind, "start");
  assert.equal(diff.filter((d) => d.type === "edge_add").length, 2);
  assert.equal(diff.filter((d) => d.type === "edge_remove").length, 1);
  assert.equal(next.edges.length, 3);
});

test("applyChanges: label があれば title と揃える", () => {
  const { next } = applyChanges(baseFlow(), { nodes: [{ id: "start", title: "新開始" }] });
  assert.equal(next.nodes[0].data.label, "新開始");
});

test("検証: 存在しないノード/ノード種別変更/つながらない接続は 400", () => {
  const f = baseFlow();
  const code = (c) => { try { applyChanges(f, c); } catch (e) { return `${e.status}:${e.code}`; } return "ok"; };
  assert.equal(code({ nodes: [{ id: "zzz", title: "x" }] }), "400:unknown_node");
  assert.equal(code({ nodes: [{ id: "a", kind: "human" }] }), "400:forbidden_node_field");
  assert.equal(code({ nodes: [{ id: "a", type: "x" }] }), "400:forbidden_node_field");
  assert.equal(code({ nodes: [{ id: "a", position: { x: 1 } }] }), "400:forbidden_node_field");
  assert.equal(code({ addEdges: [{ source: "a", target: "nope" }] }), "400:unknown_node");
  assert.equal(code({ addEdges: [{ source: "a", target: "a" }] }), "400:self_loop");
  assert.equal(code({ addEdges: [{ source: "end", target: "a" }] }), "400:invalid_edge_from_end");
  assert.equal(code({ addEdges: [{ source: "a", target: "start" }] }), "400:invalid_edge_to_start");
  assert.equal(code({ addEdges: [{ source: "start", target: "a" }] }), "400:duplicate_edge");
  assert.equal(code({ removeEdges: [{ id: "nope" }] }), "400:unknown_edge");
  assert.equal(code({}), "400:empty_changes");
  assert.equal(code({ foo: 1 }), "400:invalid_changes");
  assert.equal(code({ nodes: [{ id: "a", title: "A" }] }), "400:no_effective_change");
  assert.equal(code({ nodes: [{ id: "a", title: "" }] }), "400:invalid_title");
});

test("preview: 何も書かず、トークンと baseUpdatedAt を返す", async () => {
  const { state, deps } = mkDeps();
  const r = await previewChange(env(), deps, { flowId: FID, changes });
  assert.equal(r.ok, true);
  assert.equal(r.baseUpdatedAt, "2026-01-02T00:00:00.000Z");
  assert.match(r.confirmToken, /^[0-9a-f]{64}$/);
  assert.equal(state.syncCalls, 0);
  assert.equal(state.backups.length, 0);
});

test("許可リスト: 空は全拒否 / リスト外は 403 / 通信前に止まる", async () => {
  const { state, deps } = mkDeps();
  let fetched = 0;
  const d2 = { ...deps, fetchFlow: async () => { fetched++; return deps.fetchFlow(); } };
  await rejects(previewChange(env({ allowedFlowIds: [] }), d2, { changes }), 403, "write_disabled");
  assert.equal(fetched, 0);
  await rejects(previewChange(env({ allowedFlowIds: ["flow_other"] }), d2, { changes }), 403, "flow_not_allowed");
  await rejects(applyChange(env({ allowedFlowIds: ["flow_other"] }), d2, { changes, expectedUpdatedAt: "x", confirmToken: "y" }), 403, "flow_not_allowed");
  await rejects(previewChange(env({ anonIdSet: false }), d2, { changes }), 503, "anon_id_not_set");
  assert.equal(state.syncCalls, 0);
});

test("flowId 不一致は 400", async () => {
  const { deps } = mkDeps();
  await rejects(previewChange(env(), deps, { flowId: "flow_zzz", changes }), 400, "flow_id_mismatch");
});

test("apply 成功: バックアップ→書き込み→読み直し一致", async () => {
  const { state, deps } = mkDeps();
  const p = await previewChange(env(), deps, { flowId: FID, changes });
  const r = await applyChange(env(), deps, { flowId: FID, changes, expectedUpdatedAt: p.baseUpdatedAt, confirmToken: p.confirmToken });
  assert.equal(r.ok, true);
  assert.equal(r.verified, true);
  assert.deepEqual(state.backups[0], baseFlow());
  assert.equal(state.synced.length, 1);
  assert.equal(state.synced[0].updatedAt, "2026-02-03T04:05:06.000Z");
  assert.equal(state.flow.nodes[1].data.title, "A改");
});

test("apply: トークン・updatedAt 必須", async () => {
  const { state, deps } = mkDeps();
  await rejects(applyChange(env(), deps, { changes, expectedUpdatedAt: "x" }), 400, "confirm_token_required");
  await rejects(applyChange(env(), deps, { changes, confirmToken: "x" }), 400, "expected_updated_at_required");
  assert.equal(state.syncCalls, 0);
});

test("apply: updatedAt がずれていれば 409", async () => {
  const { state, deps } = mkDeps();
  const p = await previewChange(env(), deps, { changes });
  state.flow.updatedAt = "2026-01-03T00:00:00.000Z"; // preview 後に誰かが更新
  await rejects(applyChange(env(), deps, { changes, expectedUpdatedAt: p.baseUpdatedAt, confirmToken: p.confirmToken }), 409, "stale_updated_at");
  assert.equal(state.syncCalls, 0);
});

test("apply: 内容が変わっていれば（updatedAt 同じでも）トークン不一致 409", async () => {
  const { state, deps } = mkDeps();
  const p = await previewChange(env(), deps, { changes });
  state.flow.nodes[2].data.title = "別の人が改名";
  await rejects(applyChange(env(), deps, { changes, expectedUpdatedAt: p.baseUpdatedAt, confirmToken: p.confirmToken }), 409, "confirm_token_mismatch");
  assert.equal(state.syncCalls, 0);
});

test("apply: preview と違う changes はトークン不一致 409", async () => {
  const { state, deps } = mkDeps();
  const p = await previewChange(env(), deps, { changes });
  const other = { nodes: [{ id: "a", title: "こっそり別案" }] };
  await rejects(applyChange(env(), deps, { changes: other, expectedUpdatedAt: p.baseUpdatedAt, confirmToken: p.confirmToken }), 409, "confirm_token_mismatch");
  assert.equal(state.syncCalls, 0);
});

test("apply: 別の署名鍵のトークンは通らない", async () => {
  const { deps } = mkDeps();
  const p = await previewChange(env({ signingKey: "other" }), deps, { changes });
  await rejects(applyChange(env(), deps, { changes, expectedUpdatedAt: p.baseUpdatedAt, confirmToken: p.confirmToken }), 409, "confirm_token_mismatch");
});

test("読み直し不一致（スナップショット）は失敗として返す", async () => {
  const { deps } = mkDeps(baseFlow(), { snapshot: true });
  const p = await previewChange(env(), deps, { changes });
  await assert.rejects(
    applyChange(env(), deps, { changes, expectedUpdatedAt: p.baseUpdatedAt, confirmToken: p.confirmToken }),
    (e) => e.status === 502 && e.code === "verify_failed" && e.extra.readBackMatchesBefore === true && Boolean(e.extra.backupId),
  );
});

test("バックアップ失敗なら書かない", async () => {
  const { state, deps } = mkDeps(baseFlow(), { backupThrows: true });
  const p = await previewChange(env(), deps, { changes });
  await rejects(applyChange(env(), deps, { changes, expectedUpdatedAt: p.baseUpdatedAt, confirmToken: p.confirmToken }), 500, "backup_failed");
  assert.equal(state.syncCalls, 0);
});

test("sync 失敗は成功と言わず backupId を返す", async () => {
  const { deps } = mkDeps(baseFlow(), { syncThrows: true });
  const p = await previewChange(env(), deps, { changes });
  await assert.rejects(
    applyChange(env(), deps, { changes, expectedUpdatedAt: p.baseUpdatedAt, confirmToken: p.confirmToken }),
    (e) => e.code === "sync_failed" && Boolean(e.extra.backupId),
  );
});

test("ロールバック: バックアップへ戻して読み直し一致 / 別フローは拒否", async () => {
  const { state, deps } = mkDeps();
  const p = await previewChange(env(), deps, { changes });
  await applyChange(env(), deps, { changes, expectedUpdatedAt: p.baseUpdatedAt, confirmToken: p.confirmToken });
  const backup = state.backups[0];
  const r = await rollbackFlow(env(), deps, backup);
  assert.equal(r.verified, true);
  assert.equal(contentHash(state.flow), contentHash(baseFlow()));
  await rejects(rollbackFlow(env({ allowedFlowIds: ["flow_other"] }), deps, backup), 403, "flow_not_allowed");
  await rejects(rollbackFlow(env(), deps, { ...backup, id: "flow_other" }), 403, "flow_not_allowed");
});
