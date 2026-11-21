/**
 * FlowForge 書き込み（試作）の実通信・実保存側。ロジック本体は flowforgeWrite.ts。
 * 非公式 API（画面が使う POST /api/session → POST /api/flows/sync）。壊れうる。
 * FLOWFORGE_ANON_ID は環境変数からだけ読む。ログ・応答には出さない。
 */
import fs from "node:fs";
import { NextResponse } from "next/server";
import path from "node:path";
import {
  applyChange,
  previewChange,
  readWriteEnv,
  rollbackFlow,
  WriteError,
  type ApplyInput,
  type BackupInfo,
  type Flow,
  type WriteDeps,
} from "@/lib/flowforgeWrite";
import { FLOWFORGE_BASE, fetchFlowforgeShare, resolveShareId } from "@/lib/flowforgeShareProxy";

const UA = "jarvis-flowforge-write-proxy/0.1";

function anonId(): string {
  return (process.env.FLOWFORGE_ANON_ID || "").trim();
}

/** 外部へ返す文字列から anonId を取り除く。 */
export function scrub(text: string): string {
  const a = anonId();
  return a ? text.split(a).join("[redacted]") : text;
}

async function startSession(base: string): Promise<string> {
  const res = await fetch(`${base}/api/session`, {
    method: "POST",
    headers: { Origin: base, Referer: `${base}/`, "User-Agent": UA },
    cache: "no-store",
  });
  if (!res.ok) throw new WriteError(502, "session_failed", `session HTTP ${res.status}`);
  const cookies = res.headers
    .getSetCookie()
    .map((c) => c.split(";")[0])
    .filter(Boolean);
  return cookies.join("; ");
}

export async function syncFlowUpstream(flow: Flow): Promise<void> {
  const id = anonId();
  if (!id) throw new WriteError(503, "anon_id_not_set");
  const base = FLOWFORGE_BASE.replace(/\/$/, "");
  const post = async (cookie: string) =>
    fetch(`${base}/api/flows/sync`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Origin: base,
        Referer: `${base}/flows/${encodeURIComponent(flow.id)}`,
        "User-Agent": UA,
        ...(cookie ? { Cookie: cookie } : {}),
      },
      body: JSON.stringify({ anonId: id, flow }),
      cache: "no-store",
    });
  let res = await post(await startSession(base));
  if (res.status === 428) res = await post(await startSession(base)); // 画面と同じ: 428 ならセッション作り直し
  if (!res.ok) {
    const j = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new WriteError(
      res.status >= 400 && res.status < 600 ? res.status : 502,
      "sync_failed",
      scrub(String(j.detail ?? `HTTP ${res.status}`)).slice(0, 200),
    );
  }
}

function repoRoot(): string {
  let dir = process.cwd();
  for (let i = 0; i < 6; i++) {
    if (fs.existsSync(path.join(dir, ".git"))) return dir;
    const up = path.dirname(dir);
    if (up === dir) break;
    dir = up;
  }
  return process.cwd();
}

export function backupDir(): string {
  return (
    (process.env.FLOWFORGE_BACKUP_DIR || "").trim() ||
    path.join(repoRoot(), ".jarvis_state", "flowforge_backups")
  );
}

export async function saveBackupFile(flowId: string, flow: Flow): Promise<BackupInfo> {
  const dir = backupDir();
  fs.mkdirSync(dir, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const id = `${flowId}__${stamp}.json`;
  fs.writeFileSync(path.join(dir, id), JSON.stringify(flow, null, 2), { mode: 0o600 });
  const durable = !dir.startsWith("/tmp") && !dir.startsWith("/var/task");
  // 永続でない場所（Vercel の /tmp 等）では、応答にも全体を載せて取りこぼしを防ぐ
  return durable ? { id, durable } : { id, durable, flow };
}

export function readBackupFile(id: string): Flow {
  if (!/^flow_[A-Za-z0-9_-]+__[0-9TZ-]+\.json$/.test(id)) {
    throw new WriteError(400, "invalid_backup_id");
  }
  const p = path.join(backupDir(), id);
  if (!fs.existsSync(p)) throw new WriteError(404, "backup_not_found");
  return JSON.parse(fs.readFileSync(p, "utf8")) as Flow;
}

export type WriteArgs = {
  shareId?: string | null;
  url?: string | null;
  flowId?: string | null;
  agentId?: string | null;
  changes?: unknown;
  expectedUpdatedAt?: string | null;
  confirmToken?: string | null;
  backupId?: string | null;
};

function makeDeps(shareId: string): WriteDeps {
  return {
    fetchFlow: async () => {
      const up = await fetchFlowforgeShare(shareId);
      if (!up.ok) throw new WriteError(up.status, up.error, up.upstream);
      return (up.body as { flow: Flow }).flow;
    },
    syncFlow: syncFlowUpstream,
    saveBackup: saveBackupFile,
    now: () => new Date(),
  };
}

function resolveForWrite(a: WriteArgs): string {
  // flowId は「取り違え防止の確認用」。shareId / url / agentId があればそちらで解決する。
  const hasOther = Boolean(a.shareId || a.url || a.agentId);
  const r = resolveShareId({
    shareId: a.shareId,
    url: a.url,
    agentId: a.agentId,
    flowId: hasOther ? null : a.flowId,
  });
  if ("error" in r) throw new WriteError(r.status, r.error);
  return r.shareId;
}

export type WriteAction = "preview" | "apply" | "rollback";

/** ルートと MCP の共通入口。status と body を返す（例外は呼び出し側に出さない）。 */
export async function runWriteAction(
  action: WriteAction,
  args: WriteArgs,
): Promise<{ status: number; body: Record<string, unknown> }> {
  if ((process.env.FLOWFORGE_READ_PROXY_DISABLE || "").trim() === "1" ||
      (process.env.FLOWFORGE_WRITE_DISABLE || "").trim() === "1") {
    return { status: 503, body: { ok: false, error: "disabled" } };
  }
  try {
    const env = readWriteEnv();
    const shareId = resolveForWrite(args);
    const deps = makeDeps(shareId);
    if (action === "preview") {
      return { status: 200, body: { ...(await previewChange(env, deps, { flowId: args.flowId, changes: args.changes })), shareId } };
    }
    if (action === "apply") {
      const input: ApplyInput = {
        flowId: args.flowId,
        changes: args.changes,
        expectedUpdatedAt: args.expectedUpdatedAt,
        confirmToken: args.confirmToken,
      };
      return { status: 200, body: { ...(await applyChange(env, deps, input)), shareId } };
    }
    const backup = readBackupFile(String(args.backupId || ""));
    return { status: 200, body: { ...(await rollbackFlow(env, deps, backup)), shareId } };
  } catch (e) {
    if (e instanceof WriteError) {
      return {
        status: e.status,
        body: { ok: false, error: e.code, message: scrub(e.message), ...(e.extra ?? {}) },
      };
    }
    const msg = e instanceof Error ? e.message : String(e);
    return { status: 500, body: { ok: false, error: "internal_error", message: scrub(msg).slice(0, 200) } };
  }
}

/** REST ルート共通。認証はヘッダのみ（?key= は URL がログに残るため書き込みでは不可）。 */
export async function handleWriteRoute(
  action: WriteAction,
  request: Request,
  authorized: (h: Headers) => boolean,
) {
  if (!authorized(request.headers)) {
    const secretSet = Boolean((process.env.FLOWFORGE_READ_PROXY_KEY || "").trim());
    return NextResponse.json(
      { ok: false, error: secretSet ? "unauthorized" : "FLOWFORGE_READ_PROXY_KEY 未設定" },
      { status: secretSet ? 401 : 503 },
    );
  }
  let args: WriteArgs;
  try {
    args = (await request.json()) as WriteArgs;
  } catch {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }
  if (!args || typeof args !== "object") {
    return NextResponse.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }
  const out = await runWriteAction(action, args);
  return NextResponse.json(out.body, { status: out.status });
}
