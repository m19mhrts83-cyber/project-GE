/** 公開リポに置けない宛先を、公開ミラー（partner_contacts.json）へ folder 単位で重ねる。 */

type ContactRow = { folder: string; emails: string[] };

type PrivateContactsFile = {
  emails_by_folder?: Record<string, unknown>;
};

/** 非公開の宛先を folder 単位で重ねる。読めない・壊れた値は無視して公開分だけ返す。 */
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
  const byFolder = extra?.emails_by_folder;
  if (!byFolder || typeof byFolder !== "object") return base;
  const map = new Map<string, string[]>();
  for (const [k, v] of Object.entries(byFolder)) {
    if (!Array.isArray(v)) continue;
    const emails = v.map((x) => String(x).trim()).filter((x) => x.includes("@"));
    if (emails.length) map.set(k.normalize("NFC"), emails);
  }
  if (!map.size) return base;
  return {
    ...base,
    partners: (base.partners || []).map((c) => {
      const add = map.get(String(c.folder || "").normalize("NFC"));
      if (!add) return c;
      return { ...c, emails: [...new Set([...(c.emails || []), ...add])] };
    }),
  };
}

