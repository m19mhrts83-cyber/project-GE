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
