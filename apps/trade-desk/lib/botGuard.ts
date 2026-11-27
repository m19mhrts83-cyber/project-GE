/**
 * ボット用アカウントの権限制限（資金移動・秘密の登録だけ止める）。
 * BOT_ACCOUNT_EMAILS（カンマ区切り）に載ったメールは 403。未設定なら何も止めない。
 */
export function botEmails(env: Record<string, string | undefined> = process.env): string[] {
  return String(env.BOT_ACCOUNT_EMAILS || "")
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
}

export function isBotAccount(
  email: string | null | undefined,
  env: Record<string, string | undefined> = process.env
): boolean {
  const e = String(email || "").trim().toLowerCase();
  if (!e) return false;
  return botEmails(env).includes(e);
}

export type BotBlockKind = "money" | "secrets";

export const BOT_BLOCK_MESSAGE: Record<BotBlockKind, string> = {
  money: "ボット用アカウントでは資金移動の承認・実行・完了はできません。",
  secrets: "ボット用アカウントでは秘密の登録はできません。",
};

/** ボットなら 403 用の本文を返す。そうでなければ null。 */
export function botBlock(
  email: string | null | undefined,
  kind: BotBlockKind,
  env: Record<string, string | undefined> = process.env
): { error: string; code: "bot_forbidden" } | null {
  if (!isBotAccount(email, env)) return null;
  return { error: BOT_BLOCK_MESSAGE[kind], code: "bot_forbidden" };
}
