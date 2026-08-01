export type LaneView = "unread" | "sent" | "skipped" | "snoozed" | "activity";

export const VIEW_LABEL: Record<LaneView, string> = {
  unread: "未読",
  sent: "送信済み",
  skipped: "スキップ",
  snoozed: "後で",
  activity: "活動概要",
};

export function parseLaneView(raw: string | undefined | null): LaneView {
  const s = (raw || "").trim();
  if (s === "sent" || s === "skipped" || s === "snoozed" || s === "activity") {
    return s;
  }
  return "unread";
}

/** 未読はベースパス、それ以外は /partner/sent 形式 */
export function laneViewHref(basePath: string, view: LaneView, i?: number): string {
  const base = view === "unread" ? basePath : `${basePath}/${view}`;
  if (view === "unread" && typeof i === "number" && i > 0) {
    return `${base}?i=${i}`;
  }
  return base;
}
