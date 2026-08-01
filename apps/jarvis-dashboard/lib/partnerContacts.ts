/**
 * パートナー宛先解決（連絡先一覧のミラー）。
 * 正本は OneDrive 連絡先一覧.yaml。ミラー: config/partner_contacts.json
 */
import contacts from "@/config/partner_contacts.json";

export type PartnerContact = {
  name: string;
  folder: string;
  emails: string[];
  phones: string[];
  via_ambiguous: boolean;
};

type ContactsFile = {
  partners: PartnerContact[];
};

const DATA = contacts as ContactsFile;

function norm(s: string): string {
  return s.normalize("NFC").trim().toLowerCase();
}

export function findPartnerContact(
  partner?: string | null,
  folder?: string | null,
): PartnerContact | null {
  const p = norm(partner || "");
  const f = norm(folder || "");
  const list = DATA.partners || [];
  for (const c of list) {
    if (f && norm(c.folder) === f) return c;
  }
  for (const c of list) {
    if (p && (norm(c.name) === p || norm(c.name).includes(p) || p.includes(norm(c.name)))) {
      return c;
    }
  }
  return null;
}

/** 表示・送信用の To。from_email 優先、なければ連絡先の先頭メール */
export function resolvePartnerToEmail(opts: {
  fromEmail?: string | null;
  partner?: string | null;
  folder?: string | null;
  payload?: Record<string, unknown> | null;
}): { to: string; source: string; ambiguous: boolean; emails: string[] } {
  const from = String(opts.fromEmail || "").trim();
  if (from) {
    return { to: from, source: "from_email", ambiguous: false, emails: [from] };
  }
  const payloadEmails = opts.payload?.contact_emails;
  if (Array.isArray(payloadEmails) && payloadEmails.length) {
    const emails = payloadEmails.map((x) => String(x).trim()).filter(Boolean);
    if (emails[0]) {
      return {
        to: emails[0],
        source: "payload",
        ambiguous: emails.length > 1,
        emails,
      };
    }
  }
  const c = findPartnerContact(opts.partner, opts.folder);
  if (c?.emails?.length) {
    return {
      to: c.emails[0],
      source: "contacts",
      ambiguous: Boolean(c.via_ambiguous) || c.emails.length > 1,
      emails: c.emails,
    };
  }
  return { to: "", source: "none", ambiguous: false, emails: [] };
}
