/**
 * 定額 AI への依頼（2026-11-13 従量課金ゼロ化）。
 *
 * ダッシュボードは Supabase の ai_jobs に依頼を置いて待つだけ。Mac の係
 * （scripts/jarvis_flat_ai_worker.py）が Codex → Cursor → Claude の定額枠で作って書き戻す。
 * 従量課金の AI API は一切呼ばない。Mac が止まっていると時間内に返らない。
 *
 * 待ちきれなかったときも Mac 側は作り続ける。同じ依頼（同じ文面）を 30 分以内にもう一度出すと、
 * まだ画面に返していない結果（作成中・作成済み）を使う。一度返した結果は使い回さない（作り直しは新しい依頼）。
 */
import { createServiceClient } from "@/lib/supabase/admin";
import { flatPromptHash, type FlatImage } from "@/lib/flatAiHash";

export { flatPromptHash };
export type { FlatImage };

export type FlatAiResult =
  | { ok: true; text: string; provider: string }
  | { ok: false; error: string; pending?: boolean; jobId?: string };

const REUSE_WINDOW_MS = 30 * 60 * 1000;
const POLL_MS = 2000;
// 画面の待ち上限（120 秒）の中で 2 回続けて頼む機能（グルコン等）もあるので 55 秒で区切る
export const FLAT_AI_DEFAULT_WAIT_MS = 55_000;

export const PROVIDER_LABEL: Record<string, string> = {
  gencode: "GenCode",
  codex: "Codex",
  cursor: "Cursor",
  claude: "Claude",
};


const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

type JobRow = {
  id: string;
  status: "queued" | "running" | "done" | "error";
  result: string | null;
  provider: string | null;
  error: string | null;
  created_at: string;
  delivered_at?: string | null;
};

function finished(row: JobRow): FlatAiResult | null {
  if (row.status === "done" && (row.result || "").trim()) {
    return { ok: true, text: (row.result || "").trim(), provider: row.provider || "" };
  }
  if (row.status === "error") {
    return { ok: false, error: `定額AIで作れませんでした: ${(row.error || "").slice(0, 200)}` };
  }
  return null;
}

async function delivered(
  sb: NonNullable<ReturnType<typeof createServiceClient>>,
  id: string,
  res: FlatAiResult,
): Promise<FlatAiResult> {
  await sb.from("ai_jobs").update({ delivered_at: new Date().toISOString() }).eq("id", id);
  return res;
}

export async function flatAiGenerate(
  prompt: string,
  opts: { images?: FlatImage[]; purpose?: string; waitMs?: number } = {},
): Promise<FlatAiResult> {
  const sb = createServiceClient();
  if (!sb) return { ok: false, error: "Supabase 未設定のため定額AIに依頼できません" };
  const images = opts.images || [];
  const hash = flatPromptHash(prompt, images);
  const since = new Date(Date.now() - REUSE_WINDOW_MS).toISOString();

  let jobId = "";
  const { data: prev } = await sb
    .from("ai_jobs")
    .select("id,status,result,provider,error,created_at,delivered_at")
    .eq("prompt_hash", hash)
    .gte("created_at", since)
    .neq("status", "error")
    .is("delivered_at", null)
    .order("created_at", { ascending: false })
    .limit(1);
  const prior = (prev?.[0] as JobRow | undefined) || null;
  if (prior) {
    const done = finished(prior);
    if (done) return delivered(sb, prior.id, done);
    jobId = prior.id;
  } else {
    const { data: ins, error } = await sb
      .from("ai_jobs")
      .insert({
        prompt_hash: hash,
        purpose: opts.purpose || "reply",
        interactive: true,
        prompt,
        images: images.length ? images : null,
      })
      .select("id")
      .single();
    if (error || !ins) return { ok: false, error: "定額AIへの依頼を置けませんでした" };
    jobId = String(ins.id);
  }

  const deadline = Date.now() + (opts.waitMs ?? FLAT_AI_DEFAULT_WAIT_MS);
  while (Date.now() < deadline) {
    await sleep(POLL_MS);
    const { data } = await sb
      .from("ai_jobs")
      .select("id,status,result,provider,error,created_at")
      .eq("id", jobId)
      .maybeSingle();
    if (!data) break;
    const done = finished(data as JobRow);
    if (done) return delivered(sb, jobId, done);
  }
  return {
    ok: false,
    pending: true,
    jobId,
    error: "Macの定額AIで作成中です（1分ほど）。少し待ってからもう一度押すと結果が出ます。Macが止まっているときは再開後に作ります。",
  };
}
