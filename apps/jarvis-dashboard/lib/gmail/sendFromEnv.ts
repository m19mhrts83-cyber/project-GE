/**
 * Vercel / Server Action 用 Gmail 送信（サーバー専用 env のみ）。
 * anon / publishable キーでは送らない。
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

export function gmailSendConfigured(): boolean {
  const cred = b64ToJson("GMAIL_CREDENTIALS_B64");
  const tok =
    b64ToJson("GMAIL_ESTATE_TOKEN_B64") || b64ToJson("GMAIL_M19M_TOKEN_B64");
  return Boolean(cred && tok);
}

export async function sendGmailViaEnv(opts: {
  to: string;
  subject: string;
  body: string;
  threadId?: string | null;
}): Promise<{ id: string; threadId?: string; from: string }> {
  const cred = b64ToJson("GMAIL_CREDENTIALS_B64");
  const tok =
    b64ToJson("GMAIL_ESTATE_TOKEN_B64") || b64ToJson("GMAIL_M19M_TOKEN_B64");
  if (!cred || !tok) {
    throw new Error(
      "Gmail 送信用シークレット未設定（GMAIL_CREDENTIALS_B64 + GMAIL_ESTATE_TOKEN_B64）",
    );
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
    throw new Error("credentials.json に client_id/secret がありません");
  }

  const oauth2 = new google.auth.OAuth2(clientId, clientSecret);
  oauth2.setCredentials({
    refresh_token: String(tok.refresh_token || ""),
    access_token: tok.access_token ? String(tok.access_token) : undefined,
    expiry_date: tok.expiry_date ? Number(tok.expiry_date) : undefined,
  });

  const gmail = google.gmail({ version: "v1", auth: oauth2 });
  const profile = await gmail.users.getProfile({ userId: "me" });
  const from = profile.data.emailAddress || "";

  const rawLines = [
    `To: ${opts.to}`,
    `Subject: ${opts.subject}`,
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
  if (opts.threadId) body.threadId = opts.threadId;

  const sent = await gmail.users.messages.send({
    userId: "me",
    requestBody: body,
  });

  return {
    id: String(sent.data.id || ""),
    threadId: sent.data.threadId || undefined,
    from,
  };
}
