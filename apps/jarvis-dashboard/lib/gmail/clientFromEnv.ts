/**
 * Vercel / Server 用 Gmail OAuth クライアント。
 * 既読・画像取得で共用。トークン値はログに出さない。
 */
import { google, type gmail_v1 } from "googleapis";

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
export function tokenEnvForAccount(account: string | null | undefined): string {
  const a = (account || "admin").trim().toLowerCase();
  if (a === "estate" || a === "mail_estate") return "GMAIL_ESTATE_TOKEN_B64";
  if (a === "m19m" || a === "mail_m19m") return "GMAIL_M19M_TOKEN_B64";
  return "GMAIL_ADMIN_TOKEN_B64";
}

function credAndTok(account?: string | null): {
  cred: Record<string, unknown> | null;
  tok: Record<string, unknown> | null;
  tokName: string;
} {
  const cred = b64ToJson("GMAIL_CREDENTIALS_B64");
  const tokName = tokenEnvForAccount(account);
  let tok = b64ToJson(tokName);
  if (!tok && tokName === "GMAIL_ADMIN_TOKEN_B64") {
    return { cred, tok: null, tokName };
  }
  if (
    !tok &&
    (tokName === "GMAIL_ESTATE_TOKEN_B64" || tokName === "GMAIL_M19M_TOKEN_B64")
  ) {
    tok =
      b64ToJson("GMAIL_ESTATE_TOKEN_B64") || b64ToJson("GMAIL_M19M_TOKEN_B64");
  }
  return { cred, tok, tokName };
}

export function gmailClientConfigured(account?: string | null): boolean {
  const { cred, tok } = credAndTok(account);
  return Boolean(cred && tok);
}

export type GmailClientOk = { ok: true; gmail: gmail_v1.Gmail };
export type GmailClientErr = { ok: false; error: string; skipped?: string };
export type GmailClientResult = GmailClientOk | GmailClientErr;

export function gmailClientFromEnv(
  account?: string | null,
): GmailClientResult {
  const { cred, tok, tokName } = credAndTok(account);
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
  return { ok: true, gmail: google.gmail({ version: "v1", auth: oauth2 }) };
}
