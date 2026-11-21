/** 公開リポに置けない連絡先（メール・電話）を、公開ミラー（partner_contacts.json）へ folder 単位で重ねる。 */

type ContactRow = { name?: string; folder: string; emails: string[]; phones?: string[] };

type PrivateContactsFile = {
  emails_by_folder?: Record<string, unknown>;
  phones_by_folder?: Record<string, unknown>;
  /** 公開側の一覧に無い取引先（名前・folder）。連絡先は *_by_folder から重ねる */
  extra_partners?: unknown;
};

const nfc = (s: unknown) => String(s ?? "").normalize("NFC");

function toMap(src: unknown, keep: (x: string) => boolean): Map<string, string[]> {
  const map = new Map<string, string[]>();
  if (!src || typeof src !== "object") return map;
  for (const [k, v] of Object.entries(src as Record<string, unknown>)) {
    if (!Array.isArray(v)) continue;
    const items = v.map((x) => String(x).trim()).filter((x) => x && keep(x));
    if (items.length) map.set(nfc(k), items);
  }
  return map;
}

/** 非公開の連絡先を folder 単位で重ねる。読めない・壊れた値は無視して公開分だけ返す。 */
export function mergePrivateContacts<T extends { partners: ContactRow[] }>(
  base: T,
  privateJson: string | undefined | null,
): T {
  const raw = String(privateJson || "").trim();
  if (!raw) return base;
  let extra: PrivateContactsFile;
  try {
    extra = JSON.parse(raw) as PrivateContactsFile;
  } catch {
    return base;
  }
  if (!extra || typeof extra !== "object") return base;
  const emails = toMap(extra.emails_by_folder, (x) => x.includes("@"));
  const phones = toMap(extra.phones_by_folder, () => true);
  const extras: { name: string; folder: string }[] = [];
  if (Array.isArray(extra.extra_partners)) {
    for (const e of extra.extra_partners) {
      const folder = nfc((e as { folder?: unknown })?.folder).trim();
      if (folder) extras.push({ name: String((e as { name?: unknown })?.name ?? "").trim(), folder });
    }
  }
  if (!emails.size && !phones.size && !extras.length) return base;
  const known = new Set((base.partners || []).map((c) => nfc(c.folder)));
  const rows: ContactRow[] = [...(base.partners || [])];
  for (const e of extras) {
    if (known.has(e.folder)) continue;
    known.add(e.folder);
    rows.push({ name: e.name, folder: e.folder, emails: [], phones: [] });
  }
  return {
    ...base,
    partners: rows.map((c) => {
      const key = nfc(c.folder);
      const addE = emails.get(key);
      const addP = phones.get(key);
      if (!addE && !addP) return c;
      const out: ContactRow = { ...c };
      if (addE) out.emails = [...new Set([...(c.emails || []), ...addE])];
      if (addP) out.phones = [...new Set([...(c.phones || []), ...addP])];
      return out;
    }),
  } as T;
}
