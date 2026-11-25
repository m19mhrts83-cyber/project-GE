/**
 * 313 閉じ漏れ（外で済んだのに Todoist に残っているタスク）。
 *
 * 材料: Mac の scripts/jarvis_todoist_313_done_elsewhere.py --publish が sync_meta.todoist_313_close_leak に置く。
 * 選択: 済み（完了）／残す。記録は /api/cleanup（owner_decisions todoist_313, payload.bulk, origin=close_leak）。
 * 反映: GHA の cleanup reflect（30 分ごと）が根拠コメントを付けて Todoist を完了にする。削除はしない。
 *
 * 外部に依存しない純粋な部品（tests/closeLeak.test.ts）。
 */
import type { DecisionInput } from "./decisionContract";

export const CLOSE_LEAK_KEY = "todoist_313_close_leak";

export type CloseLeakEvidence = { folder: string; subject: string; at: string };

export type CloseLeakCard = {
  id: string;
  title: string;
  labels?: string[];
  confidence: "high" | "medium" | "low";
  streak_days?: number;
  why: string;
  evidence: CloseLeakEvidence[];
};

export type CloseLeakSnapshot = {
  v: number;
  generated_at: string;
  source?: string;
  total: number;
  cards: CloseLeakCard[];
};

export type CloseLeakAct = "close" | "keep";

export const CLOSE_LEAK_LABEL: Record<CloseLeakAct, string> = { close: "済み（完了）", keep: "残す" };

/** sync_meta の値を読む。壊れていれば null（0件と区別する） */
export function parseCloseLeak(raw: unknown): CloseLeakSnapshot | null {
  try {
    const j = (typeof raw === "string" ? JSON.parse(raw) : raw) as CloseLeakSnapshot | null;
    if (!j || !Array.isArray(j.cards)) return null;
    return j;
  } catch {
    return null;
  }
}

/** 材料を作った後に Nody で判断済みの件を外す（次の検知までに二重に出さない） */
export function pendingCards(snap: CloseLeakSnapshot, decidedIds: Iterable<string>): CloseLeakCard[] {
  const done = new Set(decidedIds);
  return snap.cards.filter((c) => c.id && !done.has(c.id));
}

export function buildCloseLeakDecisions(
  cards: CloseLeakCard[],
  choices: Record<string, CloseLeakAct>,
  nonce: string,
  decidedAt: string,
): DecisionInput[] {
  const out: DecisionInput[] = [];
  for (const c of cards) {
    const act = choices[c.id];
    if (act !== "close" && act !== "keep") continue;
    out.push({
      surface: "todoist_313",
      action: act === "close" ? "close" : "defer",
      source: "loopware",
      targetType: "todoist_task",
      targetId: c.id,
      employee: "313",
      subject: c.title,
      finalText: act,
      idemKey: `loopware:closeleak:${c.id}:${act}:${nonce}`,
      timing: { decided_at: decidedAt },
      payload: {
        bulk: true,
        origin: "close_leak",
        label: "313閉じ漏れ",
        why: c.why,
        confidence: c.confidence,
        evidence: c.evidence.slice(0, 3),
      },
      reasonTags: act === "close" ? ["外で済んだ"] : [],
    });
  }
  return out;
}
