/**
 * 自動通知・返信不可アドレス（noreply / mailer-daemon / google.com 系）への送信を弾く共通判定。
 * 送信の最終関門（sendGmailViaEnv）と、各呼び出し元の事前チェックで使う。
 */
export function isBlockedRecipient(address: string): boolean {
  const normalized = String(address || "").trim().toLowerCase();
  return /(^|[._+-])(no-?reply|noreplyto|do-?not-?reply)([._+@-]|$)|mailer-daemon|postmaster@|@(?:[a-z0-9-]+\.)*google\.com$/i.test(
    normalized,
  );
}

/** To に含まれる全アドレス（カンマ・セミコロン区切り、"名前 <addr>" 形式可）を取り出す */
export function extractRecipients(to: string): string[] {
  return String(to || "")
    .split(/[,;]/)
    .map((s) => {
      const m = s.match(/<([^>]+)>/);
      return (m ? m[1] : s).trim();
    })
    .filter(Boolean);
}

export class BlockedRecipientError extends Error {
  readonly code = "blocked_recipient";
  constructor(address: string) {
    super(`送信禁止宛先です（noreply／自動通知）: ${address}`);
    this.name = "BlockedRecipientError";
  }
}

/** 禁止宛先が含まれていれば BlockedRecipientError を投げる */
export function assertSendableRecipients(to: string): void {
  for (const addr of extractRecipients(to)) {
    if (isBlockedRecipient(addr)) throw new BlockedRecipientError(addr);
  }
}
