/**
 * Vercel / Server Action 用 Gmail 既読（UNREAD 除去）。
 * トリアージのスキップ・送信済み・対応済みに合わせて呼ぶ。
 */
import { gmailClientFromEnv } from "./clientFromEnv";

export { gmailClientConfigured as gmailMarkReadConfigured } from "./clientFromEnv";

export type MarkReadResult =
  | { ok: true; messageId: string; account: string }
  | { ok: false; skipped?: string; error?: string };

/**
 * Gmail message id を既読にする。失敗しても呼び出し側の status 更新は止めない想定。
 */
export async function markGmailReadViaEnv(opts: {
  messageId: string;
  account?: string | null;
}): Promise<MarkReadResult> {
  const messageId = (opts.messageId || "").trim();
  if (!messageId) {
    return { ok: false, skipped: "no_message_id" };
  }
  const client = gmailClientFromEnv(opts.account);
  if (!client.ok) {
    return { ok: false, skipped: client.skipped, error: client.error };
  }
  await client.gmail.users.messages.modify({
    userId: "me",
    id: messageId,
    requestBody: { removeLabelIds: ["UNREAD"] },
  });
  return {
    ok: true,
    messageId,
    account: (opts.account || "admin").trim() || "admin",
  };
}
