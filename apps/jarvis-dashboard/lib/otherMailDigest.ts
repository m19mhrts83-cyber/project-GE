/** sync_meta.other_mail_digest の JSON */

export type OtherMailActionItem = {
  id?: string;
  subject?: string;
  from?: string;
  reason?: string;
};

export type OtherMailDigest = {
  generated_at?: string;
  pending_count?: number;
  overview?: string;
  action_items?: OtherMailActionItem[];
  lines?: string[];
};

export function parseOtherMailDigest(
  raw: string | undefined | null,
): OtherMailDigest | null {
  if (!raw || !raw.trim()) return null;
  try {
    const v = JSON.parse(raw) as OtherMailDigest;
    if (!v || typeof v !== "object") return null;
    return v;
  } catch {
    return null;
  }
}
