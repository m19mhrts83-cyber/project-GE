/**
 * KURASHIFT のお金の判断（資金移動・物件）に付ける「判断メモ」。
 *
 * ループウェアの決まりごと（apps/loopware・判断ログ契約 v1）に合わせる:
 * - 理由は任意。押さなくても判断は記録する（毎回書かせない）
 * - 「今回だけ」と「次も同じに」を分ける（scope）。ルールにするかは週次で松野さんが決める
 * - 本人の理由だけを残す。AI が推測した理由で埋めない
 *
 * 書き込み先はアプリ側の表（kurashift_money_ops.assist_payload.decision_log /
 * kurashift_re_deal_events.payload）。共有の判断ログ owner_decisions へは DB トリガーが写す
 * （apps/jarvis-dashboard/supabase/migrations/20261110_kurashift_owner_decisions.sql）。
 */
import {
  DEAL_REASON_TAGS,
  DEAL_TAKE_REASON_TAGS,
  MONEY_REASON_TAGS,
} from "@/lib/decisionContract";

export type DecisionScope = "once" | "always";

export type DecisionNote = {
  reason_tags: string[];
  note: string | null;
  scope: DecisionScope;
};

export type TagOption = { key: string; label: string };

function opts(o: Record<string, string>): TagOption[] {
  return Object.entries(o).map(([key, label]) => ({ key, label }));
}

/** 判断の種類ごとに出す理由の選択肢 */
export const DECISION_TAGS = {
  money: opts(MONEY_REASON_TAGS),
  deal_pass: opts(DEAL_REASON_TAGS),
  deal_take: opts(DEAL_TAKE_REASON_TAGS),
} as const;

export type DecisionTagKind = keyof typeof DECISION_TAGS;

const ALL_KEYS = new Set<string>(
  Object.values(DECISION_TAGS).flatMap((l) => l.map((t) => t.key))
);

/** リクエストの decision を安全な形にする。無ければ null（記録は理由なしで残る） */
export function parseDecisionNote(raw: unknown): DecisionNote | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  const tags = Array.isArray(r.reason_tags)
    ? Array.from(
        new Set(
          r.reason_tags
            .map((t) => String(t || "").trim())
            .filter((t) => ALL_KEYS.has(t))
        )
      ).slice(0, 6)
    : [];
  const noteRaw = typeof r.note === "string" ? r.note.trim() : "";
  const note = noteRaw ? noteRaw.slice(0, 400) : null;
  const scope: DecisionScope = r.scope === "always" ? "always" : "once";
  if (!tags.length && !note && scope === "once") {
    return { reason_tags: [], note: null, scope };
  }
  return { reason_tags: tags, note, scope };
}

/** 資金移動の status 変化 → 判断ログの action（契約 v1 の語） */
export const MONEY_STATUS_ACTION: Record<string, string> = {
  approved: "accept", // 承認＝計画に合意（実行はまだ）
  consulting: "hesitated", // 相談に回した＝迷った
  cancelled: "reject", // 取消
  done: "done", // 寄せ完了・完了
  executing: "comment", // 実行中へ（判断ではなく進み具合）
  draft: "comment", // 草案に戻す
};

/** 判断の痕跡（kurashift_money_ops.assist_payload.decision_log の1件） */
export type MoneyDecisionEntry = {
  at: string;
  from: string;
  to: string;
  action: string;
  by: string | null;
  reason_tags: string[];
  note: string | null;
  scope: DecisionScope;
  amount_jpy: number | null;
};

const LOG_MAX = 50;

export function appendMoneyDecision(
  assist: Record<string, unknown>,
  entry: MoneyDecisionEntry
): Record<string, unknown> {
  const prev = Array.isArray(assist.decision_log) ? assist.decision_log : [];
  return {
    ...assist,
    decision_log: [...prev, entry].slice(-LOG_MAX),
    last_decision: entry,
  };
}

/** 画面表示用のラベル */
export function tagLabel(key: string): string {
  for (const list of Object.values(DECISION_TAGS)) {
    const hit = list.find((t) => t.key === key);
    if (hit) return hit.label;
  }
  return key;
}

export const MONEY_STATUS_LABEL: Record<string, string> = {
  draft: "草案",
  consulting: "相談中",
  approved: "承認",
  executing: "実行中",
  done: "完了",
  cancelled: "取消",
};
