/**
 * MQ 月次自動更新 — 流動年度・確定・月1回ゲート
 *
 * 1月: 前年＋当年を全更新
 * 2月: 前年を最終更新して確定＋当年を更新
 * 3〜12月: 当年のみ
 * 確定年度は通常処理で触らない（--reopen で明示再開）
 */

export type MqRefreshDecision = {
  /** 今回 CSV/取込・MQ置換する年度 */
  yearsToRefresh: number[];
  /** 今回の処理後に確定マークする年度（通常は2月の前年） */
  yearsToSeal: number[];
  /** 既に確定済みでスキップした年度 */
  sealedSkipped: number[];
  /** 月次サイクルキー YYYY-MM（当暦月） */
  cycleMonth: string;
  /** day>=5 かつ未実施なら true */
  shouldRunMonthly: boolean;
  reason: string;
};

function tokyoParts(now: Date) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  return {
    y: Number(parts.find((p) => p.type === "year")?.value),
    m: Number(parts.find((p) => p.type === "month")?.value),
    d: Number(parts.find((p) => p.type === "day")?.value),
  };
}

export function cycleMonthKey(now = new Date()): string {
  const { y, m } = tokyoParts(now);
  return `${y}-${String(m).padStart(2, "0")}`;
}

/** 毎月5日以降が月次締めウィンドウ（火金ランナー相乗り） */
export const MQ_MONTHLY_REFRESH_FROM_DAY = 5;

export function decideMqRefreshYears(
  opts: {
    now?: Date;
    sealedYears?: number[];
    /** 明示的に確定を外して再処理する年度 */
    reopenYears?: number[];
    /** このサイクル月で既に成功したか */
    lastSuccessCycleMonth?: string | null;
    /** 強制（ゲート無視） */
    force?: boolean;
  } = {}
): MqRefreshDecision {
  const now = opts.now ?? new Date();
  const { y, m, d } = tokyoParts(now);
  const cycleMonth = cycleMonthKey(now);
  const sealed = new Set(opts.sealedYears ?? []);
  const reopen = new Set(opts.reopenYears ?? []);
  for (const r of reopen) sealed.delete(r);

  let candidates: number[] = [];
  let yearsToSeal: number[] = [];
  let reason = "";

  if (m === 1) {
    candidates = [y - 1, y];
    reason = "1月: 前年＋当年を流動更新";
  } else if (m === 2) {
    candidates = [y - 1, y];
    yearsToSeal = [y - 1];
    reason = "2月: 前年を最終更新して確定＋当年を更新";
  } else {
    candidates = [y];
    reason = "通常月: 当年のみ更新";
  }

  const sealedSkipped: number[] = [];
  const yearsToRefresh: number[] = [];
  for (const yr of candidates) {
    if (sealed.has(yr) && !reopen.has(yr)) {
      sealedSkipped.push(yr);
      continue;
    }
    yearsToRefresh.push(yr);
  }
  // 明示 reopen は候補外でも再処理対象に含める
  for (const yr of reopen) {
    if (!yearsToRefresh.includes(yr)) yearsToRefresh.push(yr);
  }
  yearsToRefresh.sort();

  const inWindow = d >= MQ_MONTHLY_REFRESH_FROM_DAY;
  const already =
    Boolean(opts.lastSuccessCycleMonth) &&
    opts.lastSuccessCycleMonth === cycleMonth;
  const shouldRunMonthly =
    Boolean(opts.force) || (inWindow && !already && yearsToRefresh.length > 0);

  if (!opts.force) {
    if (!inWindow) {
      reason += `（${MQ_MONTHLY_REFRESH_FROM_DAY}日未満のため月次スキップ可）`;
    } else if (already) {
      reason += "（当月サイクル済み）";
    }
  }

  return {
    yearsToRefresh,
    yearsToSeal: yearsToSeal.filter((yr) => yearsToRefresh.includes(yr)),
    sealedSkipped,
    cycleMonth,
    shouldRunMonthly,
    reason,
  };
}
