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
  /** 判断メモを開いてから決めるまで（ms）。判断しにくさを見るため（L11） */
  decide_ms?: number | null;
  /** 画面が出した「前回と同じ」「よく使う」の候補（本人の理由とは分けて残す） */
  suggested_tags?: string[];
  /** 「前回と同じ」をそのまま使った */
  same_as_last?: boolean;
};

/** 後日の答え合わせ（S21 使った結果を振り返る） */
export const RETRO_QUALITY = {
  good: "良かった",
  meh: "まあまあ",
  regret: "やり直したい",
} as const;
export type RetroQuality = keyof typeof RETRO_QUALITY;

export type Retro = { at: string; quality: RetroQuality; note: string | null };

export function parseRetro(raw: unknown, now: Date = new Date()): Retro | null {
  if (!raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  const q = String(r.quality || "");
  if (!(q in RETRO_QUALITY)) return null;
  const note = typeof r.note === "string" && r.note.trim() ? r.note.trim().slice(0, 400) : null;
  return { at: now.toISOString(), quality: q as RetroQuality, note };
}

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
  const ms = Number(r.decide_ms);
  // 6時間を超えるのは開きっぱなし。数えない（契約 v1 の decideMs と同じ）
  const decide_ms = Number.isFinite(ms) && ms >= 0 && ms <= 6 * 3600_000 ? Math.round(ms) : null;
  const suggested_tags = Array.isArray(r.suggested_tags)
    ? Array.from(
        new Set(r.suggested_tags.map((t) => String(t || "").trim()).filter((t) => ALL_KEYS.has(t)))
      ).slice(0, 6)
    : [];
  return {
    reason_tags: tags,
    note,
    scope,
    decide_ms,
    suggested_tags,
    same_as_last: r.same_as_last === true,
  };
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
  decide_ms?: number | null;
  suggested_tags?: string[];
  same_as_last?: boolean;
  retro?: Retro;
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
