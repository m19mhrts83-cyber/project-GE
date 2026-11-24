/** triage_items.status — Mac 夜間トリアージと揃える */
export type TriageStatus =
  | "pending"
  | "sent"
  | "skipped"
  | "snoozed"
  | "done"; // 旧 UI 互換（対応済み）

export const UNREAD_STATUS = "pending" as const;

export const CLOSED_STATUSES: TriageStatus[] = [
  "sent",
  "skipped",
  "snoozed",
  "done",
];

export const STATUS_LABEL: Record<TriageStatus, string> = {
  pending: "未読",
  sent: "送信済み",
  skipped: "スキップ",
  snoozed: "後で",
  done: "対応済み（旧）",
};

export function isUnread(status: string | null | undefined): boolean {
  return (status || "pending") === "pending";
}

export function isClosed(status: string | null | undefined): boolean {
  return CLOSED_STATUSES.includes((status || "") as TriageStatus);
}

export const NEEDS_REVIEW_LABEL = "要確認: 送信先が返信不可アドレス";

/** 送信の最終関門が返信不可宛で止めたカード（payload.needs_review=true） */
export function needsReview(payload: unknown): boolean {
  return (
    !!payload &&
    typeof payload === "object" &&
    (payload as { needs_review?: unknown }).needs_review === true
  );
}
