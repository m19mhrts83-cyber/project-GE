/** ホーム画面の3段階色分け（見る優先度） */

export type HomeLevel = "attention" | "warn" | "info";

const WATCH_ORDER: Record<string, number> = {
  attention: 0,
  warn: 1,
  info: 2,
  ok: 9,
};

const MAIL_PRI_TO_LEVEL: Record<string, HomeLevel> = {
  high: "attention",
  medium: "warn",
  med: "warn",
  low: "info",
};

export const LEVEL_LABEL: Record<HomeLevel, string> = {
  attention: "要確認",
  warn: "注意",
  info: "参考",
};

export function watchSortKey(level: string | null | undefined): number {
  return WATCH_ORDER[level || ""] ?? 8;
}

export function mailPriorityToLevel(
  priority: string | null | undefined
): HomeLevel {
  const p = (priority || "").toLowerCase().trim();
  return MAIL_PRI_TO_LEVEL[p] || "info";
}

export function laneHref(lane: string | null | undefined): string {
  switch (lane) {
    case "partner":
      return "/partner";
    case "openchat":
      return "/openchat";
    case "general":
      return "/general";
    default:
      return "/";
  }
}

export function laneLabel(lane: string | null | undefined): string {
  switch (lane) {
    case "partner":
      return "パートナー";
    case "openchat":
      return "オプチャ";
    case "general":
      return "それ以外";
    default:
      return lane || "メール";
  }
}
