/**
 * Todoist 片付けのまとめ判断（Nody /313/bulk）の型と、確定内容 → 判断ログの行。
 * 材料は scripts/jarvis_todoist_cleanup_bulk.py の snapshot（sync_meta.todoist_cleanup_snapshot）。
 * 反映（Todoist を実際に変える）も同じスクリプトの reflect。ここは記録だけ。
 */
import type { DecisionInput } from "./decisionContract.ts";

export type Suggest = "close" | "drop" | "keep";

export type CleanupCard = {
  id: string;
  title: string;
  sender: string;
  subject: string;
  mail_date: string;
  summary: string;
  gmail_url: string;
  due: string | null;
  added_at: string;
  age_days: number | null;
  suggest: Suggest;
  why: string;
  priority?: string | number | null;
  /**
   * どこから来たカードか。
   * 318 … Todoist消化係の判断依頼（②）。scripts/jarvis_todoist_318_handoff.py が作る
   * 313 … 週の整理（金曜）の「済み？／やめてもいいのでは」。scripts/jarvis_todoist_313_weekly.py が作る。
   *       選べるのは 済み／やめる／残す だけ。やめるも完了扱い（削除しない）
   */
  origin?: "318" | "313" | "leak";
  /** 313: 済みの根拠（PR・Issue 等）へのリンク */
  evidence_url?: string | null;
  deadline?: string | null;
  /** 前回の本人判断（例: 前回: 残す（2026-11-20）） */
  prev?: string;
};

export type CleanupSnapshot = {
  v: number;
  generated_at: string;
  labels: string[];
  total: number;
  cards: CleanupCard[];
  /** 318 から足した件数 */
  from_318?: number;
  /** 313 週の整理から足した件数 */
  from_313?: number;
  from_leak?: number;
};

/** 松野さんの選択。未選択のカードは何も記録しない（おすすめは初期表示だけ） */
export type Choice = { act: "close" | "drop" | "reschedule" | "keep"; due?: string };
export type Choices = Record<string, Choice>;

export const ACT_LABEL: Record<Choice["act"], string> = {
  close: "完了",
  drop: "削除",
  reschedule: "日を変える",
  keep: "残す",
};

/** 313 週の整理のカードで出す選択肢と呼び方（やめる＝完了扱い。削除・日を変えるは出さない） */
export const ACTS_313: Choice["act"][] = ["close", "drop", "keep"];
export const ACT_LABEL_313: Record<Choice["act"], string> = {
  close: "済み",
  drop: "やめる",
  reschedule: "日を変える",
  keep: "残す",
};

export function actLabel(c: Pick<CleanupCard, "origin">, act: Choice["act"]): string {
  return c.origin === "313" || c.origin === "leak" ? ACT_LABEL_313[act] : ACT_LABEL[act];
}

/** 一覧の並び（318 → 313 → スター起票）ごとの見出し */
export function groupOf(c: Pick<CleanupCard, "origin">): "318" | "313" | "leak" | "star" {
  return c.origin === "318" || c.origin === "313" || c.origin === "leak" ? c.origin : "star";
}

export const GROUP_TITLE: Record<"318" | "313" | "leak" | "star", string> = {
  leak: "閉じ漏れ（外で済んだかも）",
  "318": "318 判断依頼（やり切る前に聞きたいこと）",
  "313": "313 週の整理（済み？／やめてもいいのでは）",
  star: "スター付きメール由来",
};

/** 契約の action: keep は defer（今回は見送り・候補に残す）で記録する */
const ACTION_OF: Record<Choice["act"], string> = { close: "close", drop: "drop", reschedule: "reschedule", keep: "defer" };

export function isDate(s: unknown): s is string {
  return typeof s === "string" && /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s));
}

export function addDaysIso(iso: string, n: number): string {
  const d = new Date(Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10) + n));
  return d.toISOString().slice(0, 10);
}

export function buildCleanupDecisions(
  cards: CleanupCard[],
  choices: Choices,
  nonce: string,
  decidedAt: string,
): DecisionInput[] {
  const out: DecisionInput[] = [];
  for (const c of cards) {
    const ch = choices[c.id];
    if (!ch) continue;
    if (ch.act === "reschedule" && !isDate(ch.due)) continue;
    if ((c.origin === "313" || c.origin === "leak") && !ACTS_313.includes(ch.act)) continue; // 313 のカードは 済み・やめる・残す だけ
    out.push({
      surface: "todoist_313",
      action: ACTION_OF[ch.act],
      source: "loopware",
      targetType: "todoist_task",
      targetId: c.id,
      employee: "313",
      subject: c.title,
      aiProposal: c.suggest,
      finalText: ch.act,
      idemKey: `loopware:cleanup:${c.id}:${ch.act}:${nonce}`,
      timing: { decided_at: decidedAt },
      payload: {
        bulk: true,
        due: ch.act === "reschedule" ? ch.due : undefined,
        why: c.why,
        sender: c.sender,
        age_days: c.age_days,
        label: c.origin === "318" ? "318判断依頼" : c.origin === "313" ? "313週の整理" : c.origin === "leak" ? "閉じ漏れ検知" : "スター起票",
        origin: c.origin,
        followed_suggest: ch.act === c.suggest,
      },
    });
  }
  return out;
}
