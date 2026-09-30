/**
 * 自分発信メール判定（scripts/jarvis_kurashift_re_inquiry_channel.py の is_self_email と同期）
 * 「その他メール／要確認」では他者着信だけを対象にし、自アドレス差出を除外する。
 */

const KNOWN_SELF_EMAILS = [
  "matsuno.estate@gmail.com",
  "admin@livingsupport-matsu.co.jp",
  "m19m.hrts83@gmail.com",
];

export function parseEmailAddr(raw: string | null | undefined): string {
  if (!raw) return "";
  const m = String(raw).match(/<([^>]+)>/);
  return (m ? m[1] : String(raw)).trim().toLowerCase();
}

export function selfEmailsExtraFromEnv(): string[] {
  const out: string[] = [];
  if (typeof process === "undefined" || !process.env) return out;
  for (const k of ["PERSONAL_EMAIL", "COMPANY_EMAIL", "INQUIRY_GROK_HANDOFF_TO"]) {
    const v = (process.env[k] || "").trim();
    if (v) out.push(v.toLowerCase());
  }
  return out;
}

/** From が自分（m19m / admin / estate / 法人ドメイン等）なら true */
export function isSelfEmail(
  email: string | null | undefined,
  extra?: string[] | null,
): boolean {
  const addr =
    parseEmailAddr(email) || String(email || "").trim().toLowerCase();
  if (!addr || !addr.includes("@")) return false;
  if (addr.endsWith("@livingsupport-matsu.co.jp")) return true;
  if (KNOWN_SELF_EMAILS.includes(addr)) return true;
  for (const e of extra || selfEmailsExtraFromEnv()) {
    if (e && addr === e.trim().toLowerCase()) return true;
  }
  return false;
}
