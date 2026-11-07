import { updateDecisionSync, type DecisionRecord } from "./storage";

export type SyncResult = {
  shared: boolean;
  /** 同じ判断の送り直しで、共有DBに行を増やさなかった */
  deduped?: boolean;
  reason?: string;
};

/**
 * 判断を /api/decide へ送り、共有DB（Supabase）に残ったかを返す。
 * 端末（localStorage）には呼ぶ前に保存済み。結果は端末の記録にも書き戻す。
 * API が ok:true でも persisted:false なら「共有DBには無い」と扱う。
 */
export async function postDecision(
  rec: DecisionRecord,
  body: Record<string, unknown>,
): Promise<SyncResult> {
  let res: SyncResult;
  try {
    const r = await fetch("/api/decide", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...body, decision: rec }),
    });
    const j = (await r.json().catch(() => ({}))) as {
      ok?: boolean;
      persisted?: boolean;
      deduped?: boolean;
      reason?: string;
      error?: string;
    };
    res =
      r.ok && j.ok && j.persisted
        ? { shared: true, deduped: !!j.deduped }
        : { shared: false, reason: j.reason || j.error || `HTTP ${r.status}` };
  } catch (e) {
    res = { shared: false, reason: e instanceof Error ? e.message : "network" };
  }
  updateDecisionSync(rec, res.shared ? "shared" : "local", res.reason);
  return res;
}

/** 画面に出す一言。共有DBに無いときははっきり分ける。 */
export function syncLabel(r: SyncResult): string {
  if (r.shared) return r.deduped ? "共有DBに保存済み（同じ判断なので増やしていない）" : "共有DBに保存した";
  return `この端末にだけ保存（共有DBには未保存: ${r.reason || "不明"}）`;
}
