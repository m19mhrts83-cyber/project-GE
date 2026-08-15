/**
 * Vercel / Server Action 用 Gmail 既読（UNREAD 除去）。
 * トリアージのスキップ・送信済み・対応済みに合わせて呼ぶ。
 */
import { google } from "googleapis";

function b64ToJson(envName: string): Record<string, unknown> | null {
  const raw = (process.env[envName] || "").trim();
  if (!raw) return null;
  try {
    const text = Buffer.from(raw, "base64").toString("utf8");
    return JSON.parse(text) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/** account 列（admin / estate / m19m）→ token env */
function tokenEnvForAccount(account: string | null | undefined): string {
  const a = (account || "admin").trim().toLowerCase();
  if (a === "estate" || a === "mail_estate") return "GMAIL_ESTATE_TOKEN_B64";
  if (a === "m19m" || a === "mail_m19m") return "GMAIL_M19M_TOKEN_B64";
  // general トリアージは admin 取込が正
  return "GMAIL_ADMIN_TOKEN_B64";
}

export function gmailMarkReadConfigured(
  account?: string | null,
): boolean {
  const cred = b64ToJson("GMAIL_CREDENTIALS_B64");
  const tokName = tokenEnvForAccount(account);
  let tok = b64ToJson(tokName);
  // admin 未設定時は estate にフォールバックしない（誤アカウント既読を避ける）
  if (!tok && tokName === "GMAIL_ADMIN_TOKEN_B64") {
    // 旧構成: admin が無い環境では何もしない（Mac catchup に任せる）
    return false;
  }
  if (!tok && (tokName === "GMAIL_ESTATE_TOKEN_B64" || tokName === "GMAIL_M19M_TOKEN_B64")) {
    tok =
      b64ToJson("GMAIL_ESTATE_TOKEN_B64") || b64ToJson("GMAIL_M19M_TOKEN_B64");
  }
  return Boolean(cred && tok);
}

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

  const cred = b64ToJson("GMAIL_CREDENTIALS_B64");
  const tokName = tokenEnvForAccount(opts.account);
  let tok = b64ToJson(tokName);
  if (
    !tok &&
    (tokName === "GMAIL_ESTATE_TOKEN_B64" || tokName === "GMAIL_M19M_TOKEN_B64")
  ) {
    tok =
      b64ToJson("GMAIL_ESTATE_TOKEN_B64") || b64ToJson("GMAIL_M19M_TOKEN_B64");
  }
  if (!cred || !tok) {
    return {
      ok: false,
      skipped: "token_missing",
      error: `${tokName} or GMAIL_CREDENTIALS_B64 missing`,
    };
  }

  const clientId = String(
    (cred.installed as { client_id?: string } | undefined)?.client_id ||
      (cred.web as { client_id?: string } | undefined)?.client_id ||
      "",
  );
  const clientSecret = String(
    (cred.installed as { client_secret?: string } | undefined)?.client_secret ||
      (cred.web as { client_secret?: string } | undefined)?.client_secret ||
      "",
  );
  if (!clientId || !clientSecret) {
    return { ok: false, error: "credentials missing client_id/secret" };
  }

  const oauth2 = new google.auth.OAuth2(clientId, clientSecret);
  oauth2.setCredentials({
    refresh_token: String(tok.refresh_token || ""),
    access_token: tok.access_token ? String(tok.access_token) : undefined,
    expiry_date: tok.expiry_date ? Number(tok.expiry_date) : undefined,
  });

  const gmail = google.gmail({ version: "v1", auth: oauth2 });
  await gmail.users.messages.modify({
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
