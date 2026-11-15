/**
 * 116 判断B（2026-11-15）: スター付き・Todoist済のメールは 116 の「後回し」で起票しない。
 *
 * スター付き＝松野さんが選んだもの。予定タスク「スター付きメール→Todoist起票」（平日 8:38）が
 * 起票し、Gmail に「Todoist済」を付ける。突き合わせの鍵は Gmail スレッドID。
 * 確かめられない時（トークンなし・API 失敗）は従来どおり作る（二重は後で消せる・漏れは気づけない）。
 */
import { gmailClientFromEnv } from "@/lib/gmail/clientFromEnv";
import { judgeStarLabels } from "@/lib/starLabels";

export type StarGuard =
  | { checked: false; reason: string }
  | { checked: true; starred: boolean; todoistDone: boolean };

export async function checkStarOrTodoistDone(opts: {
  messageId?: string | null;
  account?: string | null;
}): Promise<StarGuard> {
  const messageId = String(opts.messageId || "").trim();
  if (!messageId) return { checked: false, reason: "no_message_id" };
  const client = gmailClientFromEnv(opts.account);
  if (!client.ok) return { checked: false, reason: client.skipped || "gmail_unavailable" };
  try {
    const [msg, labels] = await Promise.all([
      client.gmail.users.messages.get({ userId: "me", id: messageId, format: "minimal" }),
      client.gmail.users.labels.list({ userId: "me" }),
    ]);
    return { checked: true, ...judgeStarLabels(msg.data.labelIds, labels.data.labels) };
  } catch (e) {
    return { checked: false, reason: `gmail_error:${String((e as Error)?.message || e).slice(0, 80)}` };
  }
}

/** スター起票側が説明欄に書く印（Gmail リンク・gmail_thread=）でオープンタスクを探す */
export async function findStarTodoistTask(
  threadId: string | null | undefined,
): Promise<{ id: string; url: string } | null> {
  const tid = String(threadId || "").trim();
  const token = (process.env.TODOIST_API_TOKEN || "").trim();
  if (!tid || !token) return null;
  try {
    const q = encodeURIComponent(`search: ${tid}`);
    const res = await fetch(`https://api.todoist.com/api/v1/tasks/filter?query=${q}&limit=5`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    const body = (await res.json()) as { results?: { id?: string; url?: string }[] };
    const hit = (body.results || [])[0];
    if (!hit?.id) return null;
    const id = String(hit.id);
    return { id, url: hit.url || `https://app.todoist.com/app/task/${encodeURIComponent(id)}` };
  } catch {
    return null;
  }
}
