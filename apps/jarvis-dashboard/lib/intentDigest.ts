/** sync_meta.intent_digest の JSON */

export type IntentTheme = {
  id?: string;
  label?: string;
  why?: string;
  keywords?: string[];
};

export type IntentPromoted = {
  triage_id?: string;
  subject?: string;
  action?: string;
  reason?: string;
};

export type IntentDigest = {
  generated_at?: string;
  via?: string;
  journal_dates?: string[];
  themes?: IntentTheme[];
  digest_notes?: string[];
  promoted?: IntentPromoted[];
  load_note?: string;
};

export function parseIntentDigest(
  raw: string | undefined | null,
): IntentDigest | null {
  if (!raw || !raw.trim()) return null;
  try {
    const v = JSON.parse(raw) as IntentDigest;
    if (!v || typeof v !== "object") return null;
    return v;
  } catch {
    return null;
  }
}
