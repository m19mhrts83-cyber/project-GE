/**
 * Vercel / Server Action 用 Gmail 送信（サーバー専用 env のみ）。
 * triage_items.account（admin / estate / m19m）に合わせてトークンを選ぶ。
 * anon / publishable キーでは送らない。
 */
import {
  gmailClientConfigured,
  gmailClientFromEnv,
  tokenEnvForAccount,
} from "@/lib/gmail/clientFromEnv";

/** いずれかの送信用トークンがあれば true（UI の送信ボタン表示用） */
export function gmailSendConfigured(account?: string | null): boolean {
  if (account) return gmailClientConfigured(account);
  return (
    gmailClientConfigured("estate") ||
    gmailClientConfigured("m19m") ||
    gmailClientConfigured("admin")
  );
}

/** 非 ASCII 件名を RFC 2047 encoded-word にする（Gmail raw 用） */
export function encodeMimeHeader(value: string): string {
  const v = String(value || "");
  if (!/[^\x00-\x7F]/.test(v)) return v;
  const b64 = Buffer.from(v, "utf8").toString("base64");
  return `=?UTF-8?B?${b64}?=`;
}

function friendlySendError(err: unknown, account: string): string {
  const msg = err instanceof Error ? err.message : String(err);
  const lower = msg.toLowerCase();
  if (lower.includes("invalid_grant") || lower.includes("invalid_rapt")) {
    const envName = tokenEnvForAccount(account);
    return (
      `Gmail トークンが失効しています（${envName} / account=${account}）。` +
      "Mac で token を再同意し、Vercel の同名シークレットを更新してください。"
    );
  }
  if (lower.includes("insufficient") || lower.includes("insufficientpermissions")) {
    return `Gmail 送信スコープ不足です（account=${account}）。gmail.send 付きで再同意してください。`;
  }
  if (lower.includes("invalid thread") || lower.includes("threadid")) {
    return (
      `スレッド ID が送信アカウントと一致しません（account=${account}）。` +
      "同一アカウントのトークンで再送するか、Jarvis に連絡してください。"
    );
  }
  return msg;
}

export async function sendGmailViaEnv(opts: {
  to: string;
  subject: string;
  body: string;
  threadId?: string | null;
  /** triage_items.account。未指定時は estate → m19m → admin の順 */
  account?: string | null;
}): Promise<{ id: string; threadId?: string; from: string; account: string }> {
  const preferred = (opts.account || "").trim().toLowerCase();
  const candidates = preferred
    ? [preferred]
    : ["estate", "m19m", "admin"];

  let lastErr: unknown = null;
  for (const account of candidates) {
    const client = gmailClientFromEnv(account);
    if (!client.ok) {
      lastErr = new Error(client.error);
      continue;
    }
    const gmail = client.gmail;
    try {
      const profile = await gmail.users.getProfile({ userId: "me" });
      const from = profile.data.emailAddress || "";

      const rawLines = [
        `To: ${opts.to}`,
        `Subject: ${encodeMimeHeader(opts.subject)}`,
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=UTF-8",
        "",
        opts.body,
      ];
      const raw = Buffer.from(rawLines.join("\r\n"), "utf8")
        .toString("base64")
        .replace(/\+/g, "-")
        .replace(/\//g, "_")
        .replace(/=+$/, "");

      const body: { raw: string; threadId?: string } = { raw };
      // threadId は同一アカウントのメールボックスのものだけ有効
      if (opts.threadId) body.threadId = opts.threadId;

      const sent = await gmail.users.messages.send({
        userId: "me",
        requestBody: body,
      });

      return {
        id: String(sent.data.id || ""),
        threadId: sent.data.threadId || undefined,
        from,
        account,
      };
    } catch (e) {
      lastErr = e;
      // preferred 指定時はフォールバックしない（誤アカウント送信防止）
      if (preferred) break;
    }
  }

  const used = preferred || candidates[0] || "estate";
  throw new Error(friendlySendError(lastErr, used));
}
