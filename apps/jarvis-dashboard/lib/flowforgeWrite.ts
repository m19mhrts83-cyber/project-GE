/**
 * FlowForge 書き込み（試作・非公式 API 利用）の中核ロジック。
 *
 * - 外部依存なし（node:crypto のみ）。通信・保存は deps で注入するのでモックでテストできる。
 * - 2段階: preview（何も書かない・確認トークン発行）→ apply（トークン＋updatedAt 必須）。
 * - 許可リスト（FLOWFORGE_WRITE_ALLOWED_FLOW_IDS）にあるフロー ID だけ。既定は空＝全拒否。
 * - 書き込み後は必ず読み直して一致を確認。一致しなければ失敗として返す。
 * 詳細: docs/AIエージェントチーム/54b_FlowForge読取プロキシ_OpenAPI_20261106.md「書き込み（試作）」
 */
import { createHash, createHmac, timingSafeEqual } from "node:crypto";

// ───────── 型 ─────────

export type FlowNode = {
  id: string;
  data: Record<string, unknown>;
  [k: string]: unknown;
};
export type FlowEdge = { id: string; source: string; target: string; [k: string]: unknown };
export type Flow = {
  id: string;
  name?: string;
  description?: string;
  nodes: FlowNode[];
  edges: FlowEdge[];
  createdAt?: string;
  updatedAt?: string;
  look?: unknown;
  [k: string]: unknown;
};

export type NodeChange = { id: string; title?: string; description?: string };
export type EdgeRef = { id?: string; source?: string; target?: string };
export type ChangeSet = {
  nodes?: NodeChange[];
  addEdges?: Array<{ source: string; target: string }>;
  removeEdges?: EdgeRef[];
};

export type DiffItem =
  | { type: "node_title"; nodeId: string; before: string; after: string }
  | { type: "node_description"; nodeId: string; before: string; after: string }
  | { type: "edge_add"; edgeId: string; source: string; target: string }
  | { type: "edge_remove"; edgeId: string; source: string; target: string };

export class WriteError extends Error {
  status: number;
  code: string;
  extra?: Record<string, unknown>;
  constructor(status: number, code: string, message?: string, extra?: Record<string, unknown>) {
    super(message || code);
    this.status = status;
    this.code = code;
    this.extra = extra;
  }
}

export type WriteEnv = {
  allowedFlowIds: string[];
  anonIdSet: boolean;
  signingKey: string;
};

export type BackupInfo = { id: string; durable: boolean; flow?: Flow };

export type WriteDeps = {
  /** 現在のフロー（共有 API 経由）を取得。 */
  fetchFlow: () => Promise<Flow>;
  /** 非公式 sync API で保存（anonId は呼び出し側が内部で持つ）。失敗は WriteError か Error を投げる。 */
  syncFlow: (flow: Flow) => Promise<void>;
  /** 書き込み前のフロー全体を保存。失敗したら例外（その場合は書かない）。 */
  saveBackup: (flowId: string, flow: Flow) => Promise<BackupInfo>;
  now: () => Date;
};

// ───────── 環境 ─────────

export function parseAllowList(raw: string | undefined | null): string[] {
  return (raw || "")
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter((s) => /^flow_[A-Za-z0-9_-]+$/.test(s));
}

export function readWriteEnv(env: Record<string, string | undefined> = process.env): WriteEnv {
  return {
    allowedFlowIds: parseAllowList(env.FLOWFORGE_WRITE_ALLOWED_FLOW_IDS),
    anonIdSet: Boolean((env.FLOWFORGE_ANON_ID || "").trim()),
    signingKey: (env.FLOWFORGE_READ_PROXY_KEY || "").trim(),
  };
}

export function assertWriteAllowed(env: WriteEnv, flowId: string | null | undefined): void {
  if (!env.signingKey) throw new WriteError(503, "proxy_key_not_set");
  if (!env.anonIdSet) throw new WriteError(503, "anon_id_not_set");
  if (env.allowedFlowIds.length === 0) {
    throw new WriteError(403, "write_disabled", "許可リストが空のため書き込みは全拒否です");
  }
  if (!flowId || !env.allowedFlowIds.includes(flowId)) {
    throw new WriteError(403, "flow_not_allowed", "このフローは書き込み許可リストにありません");
  }
}

// ───────── ハッシュ ─────────

export function stableStringify(v: unknown): string {
  if (v === null || typeof v !== "object") return JSON.stringify(v) ?? "null";
  if (Array.isArray(v)) return `[${v.map(stableStringify).join(",")}]`;
  const o = v as Record<string, unknown>;
  const keys = Object.keys(o)
    .filter((k) => o[k] !== undefined)
    .sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(o[k])}`).join(",")}}`;
}

/** 画面の自動保存と同じ観点（nodes, edges, name, description, look）の内容ハッシュ。updatedAt は含めない。 */
export function contentHash(flow: Flow): string {
  return createHash("sha256")
    .update(
      stableStringify({
        n: flow.nodes,
        e: flow.edges,
        name: flow.name ?? "",
        d: flow.description ?? "",
        look: flow.look ?? null,
      }),
    )
    .digest("hex");
}

export function makeConfirmToken(
  key: string,
  flowId: string,
  baseHash: string,
  newHash: string,
): string {
  return createHmac("sha256", key)
    .update(`flowforge-write-v1|${flowId}|${baseHash}|${newHash}`)
    .digest("hex");
}

function tokenEquals(a: string, b: string): boolean {
  const ba = Buffer.from(a);
  const bb = Buffer.from(b);
  return ba.length === bb.length && timingSafeEqual(ba, bb);
}

// ───────── 変更の検証と適用（純粋関数） ─────────

const MAX_CHANGES = 50;
const MAX_TITLE = 200;
const MAX_DESC = 4000;
const NODE_KEYS = new Set(["id", "title", "description"]);
const EDGE_ADD_KEYS = new Set(["source", "target"]);
const EDGE_RM_KEYS = new Set(["id", "source", "target"]);
const CHANGESET_KEYS = new Set(["nodes", "addEdges", "removeEdges"]);

function bad(code: string, message: string, extra?: Record<string, unknown>): never {
  throw new WriteError(400, code, message, extra);
}

function isObj(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

function edgeIdFor(source: string, target: string): string {
  return `edge_cp_${createHash("sha1").update(`${source}>${target}`).digest("hex").slice(0, 10)}`;
}

function nodeKind(n: FlowNode): string {
  return String((n.data as Record<string, unknown>)?.kind ?? "");
}

export function validateFlowShape(flow: unknown): asserts flow is Flow {
  if (!isObj(flow) || typeof flow.id !== "string" || !Array.isArray(flow.nodes) || !Array.isArray(flow.edges)) {
    throw new WriteError(502, "upstream_flow_malformed", "取得したフローの形が想定外です");
  }
}

/** 変更案を現在のフローに当てる。元は変更しない。不正なら 400。 */
export function applyChanges(
  base: Flow,
  changes: unknown,
): { next: Flow; diff: DiffItem[] } {
  if (!isObj(changes)) bad("invalid_changes", "changes はオブジェクトで指定してください");
  for (const k of Object.keys(changes)) {
    if (!CHANGESET_KEYS.has(k)) bad("invalid_changes", `未対応の項目: ${k}`);
  }
  const nodeChanges = (changes.nodes ?? []) as unknown;
  const addEdges = (changes.addEdges ?? []) as unknown;
  const removeEdges = (changes.removeEdges ?? []) as unknown;
  if (!Array.isArray(nodeChanges) || !Array.isArray(addEdges) || !Array.isArray(removeEdges)) {
    bad("invalid_changes", "nodes / addEdges / removeEdges は配列です");
  }
  const total = nodeChanges.length + addEdges.length + removeEdges.length;
  if (total === 0) bad("empty_changes", "変更がありません");
  if (total > MAX_CHANGES) bad("too_many_changes", `一度に ${MAX_CHANGES} 件まで`);

  const next = JSON.parse(JSON.stringify(base)) as Flow;
  const diff: DiffItem[] = [];
  const byId = new Map(next.nodes.map((n) => [n.id, n]));
  const touchedNodes = new Set<string>();

  for (const raw of nodeChanges) {
    if (!isObj(raw)) bad("invalid_node_change", "nodes の要素が不正です");
    for (const k of Object.keys(raw)) {
      if (!NODE_KEYS.has(k)) {
        bad("forbidden_node_field", `ノードの変更は title / description のみ。不可: ${k}`, { field: k });
      }
    }
    const id = raw.id;
    if (typeof id !== "string" || !byId.has(id)) {
      bad("unknown_node", "存在しないノード ID です", { nodeId: String(id) });
    }
    if (touchedNodes.has(id)) bad("duplicate_node_change", "同じノードを2回変更できません", { nodeId: id });
    touchedNodes.add(id);
    if (raw.title === undefined && raw.description === undefined) {
      bad("empty_node_change", "title か description を指定してください", { nodeId: id });
    }
    const node = byId.get(id)!;
    const data = node.data as Record<string, unknown>;
    if (raw.title !== undefined) {
      if (typeof raw.title !== "string" || !raw.title.trim() || raw.title.length > MAX_TITLE) {
        bad("invalid_title", `title は1〜${MAX_TITLE}文字の文字列`, { nodeId: id });
      }
      const before = String(data.title ?? "");
      if (before !== raw.title) {
        data.title = raw.title;
        if (typeof data.label === "string") data.label = raw.title;
        diff.push({ type: "node_title", nodeId: id, before, after: raw.title });
      }
    }
    if (raw.description !== undefined) {
      if (typeof raw.description !== "string" || raw.description.length > MAX_DESC) {
        bad("invalid_description", `description は${MAX_DESC}文字以内の文字列`, { nodeId: id });
      }
      const before = String(data.description ?? "");
      if (before !== raw.description) {
        data.description = raw.description;
        diff.push({ type: "node_description", nodeId: id, before, after: raw.description });
      }
    }
  }

  for (const raw of removeEdges) {
    if (!isObj(raw)) bad("invalid_edge_ref", "removeEdges の要素が不正です");
    for (const k of Object.keys(raw)) {
      if (!EDGE_RM_KEYS.has(k)) bad("invalid_edge_ref", `未対応の項目: ${k}`);
    }
    const idx = next.edges.findIndex((e) =>
      typeof raw.id === "string"
        ? e.id === raw.id
        : typeof raw.source === "string" && typeof raw.target === "string"
          ? e.source === raw.source && e.target === raw.target
          : false,
    );
    if (idx < 0) bad("unknown_edge", "削除対象の接続が見つかりません", { edge: raw });
    const [removed] = next.edges.splice(idx, 1);
    diff.push({ type: "edge_remove", edgeId: removed.id, source: removed.source, target: removed.target });
  }

  for (const raw of addEdges) {
    if (!isObj(raw)) bad("invalid_edge", "addEdges の要素が不正です");
    for (const k of Object.keys(raw)) {
      if (!EDGE_ADD_KEYS.has(k)) bad("invalid_edge", `未対応の項目: ${k}`);
    }
    const { source, target } = raw;
    if (typeof source !== "string" || typeof target !== "string") {
      bad("invalid_edge", "source と target が必要です");
    }
    const s = byId.get(source);
    const t = byId.get(target);
    if (!s || !t) bad("unknown_node", "接続先／接続元のノードが存在しません", { source, target });
    if (source === target) bad("self_loop", "自分自身への接続は不可です", { source });
    if (nodeKind(s) === "end") bad("invalid_edge_from_end", "end ノードからは接続できません", { source });
    if (nodeKind(t) === "start") bad("invalid_edge_to_start", "start ノードへは接続できません", { target });
    if (next.edges.some((e) => e.source === source && e.target === target)) {
      bad("duplicate_edge", "同じ接続が既にあります", { source, target });
    }
    const id = edgeIdFor(source, target);
    if (next.edges.some((e) => e.id === id)) bad("duplicate_edge", "接続 ID が衝突しました", { source, target });
    next.edges.push({ id, source, target });
    diff.push({ type: "edge_add", edgeId: id, source, target });
  }

  if (diff.length === 0) bad("no_effective_change", "現在の内容と同じため変更がありません");
  return { next, diff };
}

// ───────── preview / apply ─────────

export type PreviewResult = {
  ok: true;
  flowId: string;
  baseUpdatedAt: string | null;
  baseHash: string;
  diff: DiffItem[];
  confirmToken: string;
  note: string;
};

export type ApplyInput = {
  flowId?: string | null;
  changes: unknown;
  expectedUpdatedAt?: string | null;
  confirmToken?: string | null;
};

async function loadAndPlan(env: WriteEnv, deps: WriteDeps, flowIdHint: string | null | undefined, changes: unknown) {
  const base = await deps.fetchFlow();
  validateFlowShape(base);
  if (flowIdHint && flowIdHint !== base.id) {
    throw new WriteError(400, "flow_id_mismatch", "指定の flowId と共有リンクのフローが一致しません");
  }
  assertWriteAllowed(env, base.id);
  const { next, diff } = applyChanges(base, changes);
  const baseHash = contentHash(base);
  const newHash = contentHash(next);
  const confirmToken = makeConfirmToken(env.signingKey, base.id, baseHash, newHash);
  return { base, next, diff, baseHash, newHash, confirmToken };
}

export async function previewChange(
  env: WriteEnv,
  deps: WriteDeps,
  input: { flowId?: string | null; changes: unknown },
): Promise<PreviewResult> {
  // 許可リストの空判定は fetch 前にも行う（外部通信を無駄に出さない）
  if (env.allowedFlowIds.length === 0) assertWriteAllowed(env, null);
  const p = await loadAndPlan(env, deps, input.flowId, input.changes);
  return {
    ok: true,
    flowId: p.base.id,
    baseUpdatedAt: p.base.updatedAt ?? null,
    baseHash: p.baseHash,
    diff: p.diff,
    confirmToken: p.confirmToken,
    note: "何も書いていません。松野さんが会話で明示的に承認した後だけ、同じ changes と expectedUpdatedAt（= baseUpdatedAt）と confirmToken で apply を呼ぶ。",
  };
}

export type ApplyResult = {
  ok: true;
  flowId: string;
  diff: DiffItem[];
  backup: BackupInfo;
  verified: true;
  updatedAt: string | null;
  note: string;
};

export async function applyChange(
  env: WriteEnv,
  deps: WriteDeps,
  input: ApplyInput,
): Promise<ApplyResult> {
  if (env.allowedFlowIds.length === 0) assertWriteAllowed(env, null);
  if (!input.confirmToken) throw new WriteError(400, "confirm_token_required");
  if (!input.expectedUpdatedAt) throw new WriteError(400, "expected_updated_at_required");

  const p = await loadAndPlan(env, deps, input.flowId, input.changes);
  if ((p.base.updatedAt ?? "") !== input.expectedUpdatedAt) {
    throw new WriteError(409, "stale_updated_at", "フローが preview 後に更新されています。preview をやり直してください", {
      currentUpdatedAt: p.base.updatedAt ?? null,
    });
  }
  if (!tokenEquals(p.confirmToken, input.confirmToken)) {
    throw new WriteError(409, "confirm_token_mismatch", "確認トークンが一致しません（変更内容か元のフローが preview と違います）");
  }

  let backup: BackupInfo;
  try {
    backup = await deps.saveBackup(p.base.id, p.base);
  } catch {
    throw new WriteError(500, "backup_failed", "バックアップを保存できなかったため書き込みしていません");
  }

  const toWrite: Flow = { ...p.next, updatedAt: deps.now().toISOString() };
  try {
    await deps.syncFlow(toWrite);
  } catch (e) {
    const ex =
      e instanceof WriteError
        ? e
        : new WriteError(502, "sync_failed", e instanceof Error ? e.message : String(e));
    throw new WriteError(ex.status >= 400 ? ex.status : 502, "sync_failed", ex.message, {
      backupId: backup.id,
      written: "unknown",
    });
  }

  // 読み直して検証（保存と反映確認は別。一致しなければ失敗）
  let after: Flow | null = null;
  let readErr = "";
  try {
    after = await deps.fetchFlow();
    validateFlowShape(after);
  } catch (e) {
    readErr = e instanceof Error ? e.message : String(e);
    after = null;
  }
  if (!after) {
    throw new WriteError(502, "verify_failed", "書き込み後の読み直しに失敗しました。反映は未確認です", {
      backupId: backup.id,
      reason: readErr.slice(0, 200),
    });
  }
  if (contentHash(after) !== contentHash(toWrite)) {
    throw new WriteError(
      502,
      "verify_failed",
      "読み直した内容が書き込んだ内容と一致しません（共有リンクがスナップショットの可能性）。成功とは扱いません",
      {
        backupId: backup.id,
        readBackMatchesBefore: contentHash(after) === p.baseHash,
      },
    );
  }
  return {
    ok: true,
    flowId: p.base.id,
    diff: p.diff,
    backup,
    verified: true,
    updatedAt: after.updatedAt ?? null,
    note: "書き込みと読み直し一致を確認済み。画面（ブラウザ）側のローカル保存は更新されない点に注意。",
  };
}

/** バックアップのフローを書き戻す（ロールバック）。許可リスト・読み直し検証は apply と同じ。 */
export async function rollbackFlow(
  env: WriteEnv,
  deps: Pick<WriteDeps, "fetchFlow" | "syncFlow" | "now">,
  backupFlow: unknown,
): Promise<{ ok: true; flowId: string; verified: true }> {
  validateFlowShape(backupFlow);
  assertWriteAllowed(env, backupFlow.id);
  const current = await deps.fetchFlow();
  validateFlowShape(current);
  if (current.id !== backupFlow.id) {
    throw new WriteError(400, "flow_id_mismatch", "バックアップと共有リンクのフローが一致しません");
  }
  const toWrite: Flow = { ...backupFlow, updatedAt: deps.now().toISOString() };
  await deps.syncFlow(toWrite);
  const after = await deps.fetchFlow();
  validateFlowShape(after);
  if (contentHash(after) !== contentHash(toWrite)) {
    throw new WriteError(502, "verify_failed", "ロールバック後の読み直しが一致しません");
  }
  return { ok: true, flowId: backupFlow.id, verified: true };
}
