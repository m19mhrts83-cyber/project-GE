/**
 * Todoist の件名に「誰が入れたか」の印を付ける（2026-11-10 松野さん決定）。
 * 🤖 = AI が自分の判断で入れた／🦾依頼 = 松野さんが頼んで入れた（ボタン・昇格）／印なし = 松野さん本人。
 * Python 側は scripts/jarvis_todoist_mark.py。重複確認は stripTodoistMark を通して比べる。
 */
export const AI_MARK = "🤖";
export const REQUESTED_MARK = "🦾依頼";
export type TodoistMark = "ai" | "requested" | "none";

const MARKS = [REQUESTED_MARK, AI_MARK];

export function stripTodoistMark(title: string): string {
  const s = String(title || "").trim();
  for (const m of MARKS) {
    if (s.startsWith(m)) return s.slice(m.length).trim();
  }
  return s;
}

export function markTodoistTitle(title: string, mark: TodoistMark = "ai"): string {
  const s = String(title || "").trim();
  if (mark === "none") return s;
  if (MARKS.some((m) => s.startsWith(m))) return s;
  return `${mark === "requested" ? REQUESTED_MARK : AI_MARK} ${s}`;
}
