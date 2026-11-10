import { timingSafeEqual } from "crypto";
import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * 復旧窓口（ホーク・番頭さん用）。許可した4本の GHA だけ、窓口経由で再実行できる。
 * - 2人に渡すのは窓口用の鍵（JOB_RECOVERY_KEYS）だけ。GitHub トークンはサーバー側（JOB_RECOVERY_GITHUB_TOKEN）に置く
 * - 同じジョブは6時間に1回まで（sync_meta の recovery_lock:<job> を条件つき更新で取る＝二重起動を弾く）
 * - 実行中・2回続けて失敗（認証切れなどの疑い）は再実行しない → Jarvis／松野さんへ
 * - 受付は #ai-hub に1行。結果はワークフロー側（scripts/jarvis_job_finish.sh）が1行
 * 正本: docs/AIエージェントチーム/58_ジョブ復旧窓口_ホーク番頭_20261111.md
 */

export type RecoveryJob = {
  id: string;
  label: string;
  workflow: string;
  inputs: Record<string, string>;
};

export const RECOVERY_JOBS: Record<string, RecoveryJob> = {
  comm_write: {
    id: "comm_write",
    label: "台帳書き込み（Gmail triage・未返信）",
    workflow: "jarvis-dashboard-gmail-triage.yml",
    inputs: { dry_run: "false" },
  },
  comm_reconcile: {
    id: "comm_reconcile",
    label: "台帳の突き合わせ",
    workflow: "jarvis-comm-reconcile.yml",
    inputs: {},
  },
  reply_211: {
    id: "reply_211",
    label: "211 返信案内・朝便",
    workflow: "jarvis-reply-draft-211.yml",
    inputs: { dry_run: "false" },
  },
  partner_111: {
    id: "partner_111",
    label: "111 パートナー昼便",
    workflow: "jarvis-partner-day-report.yml",
    inputs: { dry_run: "false" },
  },
};

export const LOCK_HOURS = 6;

/** 許可した4本だけを返す（"__proto__" などのキーでプロトタイプを拾わない）。 */
export function jobById(id: unknown): RecoveryJob | undefined {
  return typeof id === "string" && Object.prototype.hasOwnProperty.call(RECOVERY_JOBS, id)
    ? RECOVERY_JOBS[id]
    : undefined;
}
const ACTOR_RE = /^[a-z][a-z0-9_-]{1,23}$/;

/** "hawk:xxxx,banto:yyyy" → [{actor, key}]。形の崩れた項目は捨てる。 */
export function parseActorKeys(raw: string | undefined): { actor: string; key: string }[] {
  return (raw || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => {
      const i = s.indexOf(":");
      return { actor: s.slice(0, i).trim().toLowerCase(), key: s.slice(i + 1).trim() };
    })
    .filter((x) => ACTOR_RE.test(x.actor) && x.key.length >= 24);
}

function safeEqual(a: string, b: string): boolean {
  const x = Buffer.from(a);
  const y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}

/** Bearer の鍵から押した人を決める。合わなければ null。 */
export function actorForKey(supplied: string, raw = process.env.JOB_RECOVERY_KEYS): string | null {
  const s = supplied.trim();
  if (!s) return null;
  let hit: string | null = null;
  for (const { actor, key } of parseActorKeys(raw)) {
    if (safeEqual(key, s)) hit = actor; // 全件比べる（時間差を出さない）
  }
  return hit;
}

export function bearerOf(header: string | null): string {
  return (header || "").replace(/^Bearer\s+/i, "").trim();
}

export type RunSummary = {
  status: string; // queued / in_progress / completed …
  conclusion: string | null; // success / failure / cancelled / skipped …
  created_at: string;
  html_url: string;
  event: string;
};

export type Decision =
  | { ok: true }
  | { ok: false; reason: "in_progress" | "two_failures" | "rate_limited"; message: string };

/** 再実行してよいか（ロック以外の判断。純関数）。runs は新しい順。 */
export function decideRecovery(runs: RunSummary[]): Decision {
  if (runs.some((r) => r.status !== "completed")) {
    return { ok: false, reason: "in_progress", message: "いま実行中です。終わるのを待ってください" };
  }
  const done = runs.filter((r) => r.conclusion !== "skipped" && r.conclusion !== "cancelled");
  if (done.length >= 2 && done[0].conclusion === "failure" && done[1].conclusion === "failure") {
    return {
      ok: false,
      reason: "two_failures",
      message: "2回続けて失敗しています。認証切れなどの可能性があるので、Jarvis／松野さんへ回してください",
    };
  }
  return { ok: true };
}

/** ロックが空いているか（純関数）。 */
export function lockFree(lockedAt: string | null, now: Date, hours = LOCK_HOURS): boolean {
  if (!lockedAt) return true;
  const t = Date.parse(lockedAt);
  if (Number.isNaN(t)) return true;
  return now.getTime() - t >= hours * 3600_000;
}

/**
 * recovery_lock:<job> を取る。取れたら true。
 * 1) 行が無ければ insert（衝突なら何もしない）→ 2) あれば「6時間より古いときだけ」update。
 * どちらも1文で決まるので、同時に押されても片方しか取れない。
 */
export async function acquireLock(
  supabase: SupabaseClient,
  job: string,
  actor: string,
  now: Date,
  hours = LOCK_HOURS,
): Promise<boolean> {
  const key = `recovery_lock:${job}`;
  const value = JSON.stringify({ at: now.toISOString(), actor });
  const ins = await supabase
    .from("sync_meta")
    .upsert({ key, value, updated_at: now.toISOString() }, { onConflict: "key", ignoreDuplicates: true })
    .select("key");
  if (ins.error) throw new Error(`lock_insert:${ins.error.message}`);
  if ((ins.data || []).length > 0) return true;
  const cutoff = new Date(now.getTime() - hours * 3600_000).toISOString();
  const up = await supabase
    .from("sync_meta")
    .update({ value, updated_at: now.toISOString() })
    .eq("key", key)
    .lte("updated_at", cutoff)
    .select("key");
  if (up.error) throw new Error(`lock_update:${up.error.message}`);
  return (up.data || []).length > 0;
}

export async function releaseLock(supabase: SupabaseClient, job: string): Promise<void> {
  // dispatch に失敗したときだけ戻す（押せなかったのに6時間塞がないように）
  await supabase
    .from("sync_meta")
    .update({ updated_at: new Date(0).toISOString() })
    .eq("key", `recovery_lock:${job}`);
}

const REPO = () => (process.env.GITHUB_REPOSITORY || "m19mhrts83-cyber/project-GE").trim();
const ghHeaders = () => ({
  Accept: "application/vnd.github+json",
  Authorization: `Bearer ${(process.env.JOB_RECOVERY_GITHUB_TOKEN || "").trim()}`,
  "X-GitHub-Api-Version": "2022-11-28",
});

export function githubConfigured(): boolean {
  return Boolean((process.env.JOB_RECOVERY_GITHUB_TOKEN || "").trim());
}

export async function recentRuns(workflow: string, n = 5): Promise<RunSummary[]> {
  const res = await fetch(
    `https://api.github.com/repos/${REPO()}/actions/workflows/${workflow}/runs?per_page=${n}`,
    { headers: ghHeaders(), cache: "no-store" },
  );
  if (!res.ok) throw new Error(`github_runs_${res.status}`);
  const body = (await res.json()) as { workflow_runs?: Record<string, unknown>[] };
  return (body.workflow_runs || []).map((r) => ({
    status: String(r.status || ""),
    conclusion: (r.conclusion as string | null) ?? null,
    created_at: String(r.created_at || ""),
    html_url: String(r.html_url || ""),
    event: String(r.event || ""),
  }));
}

export async function dispatch(job: RecoveryJob, actor: string): Promise<void> {
  const res = await fetch(
    `https://api.github.com/repos/${REPO()}/actions/workflows/${job.workflow}/dispatches`,
    {
      method: "POST",
      headers: ghHeaders(),
      body: JSON.stringify({ ref: "main", inputs: { ...job.inputs, recovery_actor: actor } }),
    },
  );
  if (res.status !== 204 && !res.ok) throw new Error(`github_dispatch_${res.status}`);
}

export function jstLabel(d: Date): string {
  return new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

/** #ai-hub に1行（Webhook）。失敗しても本処理は止めない。 */
export async function postHub(text: string): Promise<void> {
  const url = (process.env.SLACK_WEBHOOK_AI_TEAM_HUB || "").trim();
  if (!url) return;
  try {
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, username: "Jarvis 復旧窓口" }),
    });
  } catch {
    /* noop */
  }
}

export async function readHeartbeats(
  supabase: SupabaseClient,
): Promise<Record<string, { at: string | null; source: string | null }>> {
  const keys = [
    ...Object.keys(RECOVERY_JOBS).map((j) => `job_ok:${j}`),
    "job_ok:comm_write_backup",
    ...Object.keys(RECOVERY_JOBS).map((j) => `recovery_lock:${j}`),
  ];
  const { data, error } = await supabase.from("sync_meta").select("key,value,updated_at").in("key", keys);
  if (error) throw new Error(`heartbeat:${error.message}`);
  const out: Record<string, { at: string | null; source: string | null }> = {};
  for (const row of data || []) {
    let v: { at?: string; source?: string; actor?: string } = {};
    try {
      v = JSON.parse(String(row.value || "{}"));
    } catch {
      v = {};
    }
    out[String(row.key)] = {
      at: v.at || (row.updated_at as string) || null,
      source: v.source || v.actor || null,
    };
  }
  return out;
}
