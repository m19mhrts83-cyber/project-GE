/** 116 判断B: Gmail ラベルからスター付き・Todoist済を判定（ネットワーク不要） */
export const TODOIST_DONE_LABEL = "Todoist済";

/** labelIds とラベル一覧から判定（ネットワーク不要・テスト用に分離） */
export function judgeStarLabels(
  labelIds: string[] | null | undefined,
  labels: { id?: string | null; name?: string | null }[] | null | undefined,
): { starred: boolean; todoistDone: boolean } {
  const ids = new Set(labelIds || []);
  const doneId = (labels || []).find((l) => l.name === TODOIST_DONE_LABEL)?.id || "";
  return { starred: ids.has("STARRED"), todoistDone: Boolean(doneId && ids.has(doneId)) };
}
