/** 神大家オプチャ digest / グループ slug */

export type OpenchatDigestGroup = {
  name: string;
  slug: string;
  lines: string[];
  updated_at?: string | null;
  count?: number;
};

export type OpenchatDigest = {
  generated_at?: string;
  overview?: string;
  groups: OpenchatDigestGroup[];
  via?: string;
};

export function slugifyGroup(name: string): string {
  return encodeURIComponent(name.trim().replace(/\s+/g, "_"));
}

export function parseOpenchatDigest(
  raw: string | undefined,
): OpenchatDigest | null {
  if (!raw) return null;
  try {
    const j = JSON.parse(raw) as OpenchatDigest;
    if (!Array.isArray(j.groups)) return null;
    return j;
  } catch {
    return null;
  }
}

export type ActivityRow = {
  id: string;
  partner: string | null;
  folder: string | null;
  subject: string | null;
  summary: string | null;
  received_at: string | null;
  channel: string | null;
};

export type GroupBundle = {
  name: string;
  slug: string;
  count: number;
  latestAt: string | null;
  lines: string[];
  folder: string | null;
  digestLines?: string[];
};

export function bundleByGroup(
  activities: ActivityRow[],
  digest: OpenchatDigest | null,
): GroupBundle[] {
  const map = new Map<string, GroupBundle>();
  for (const a of activities) {
    const name = (a.partner || "（不明）").trim() || "（不明）";
    const slug = slugifyGroup(name);
    const b = map.get(name) || {
      name,
      slug,
      count: 0,
      latestAt: null as string | null,
      lines: [] as string[],
      folder: a.folder,
    };
    b.count += 1;
    if (
      !b.latestAt ||
      String(a.received_at || "") > String(b.latestAt || "")
    ) {
      b.latestAt = a.received_at;
    }
    if (!b.folder && a.folder) b.folder = a.folder;
    const line = (a.summary || a.subject || "").replace(/\s+/g, " ").trim();
    if (line && b.lines.length < 4) b.lines.push(line.slice(0, 160));
    map.set(name, b);
  }

  const digestByName = new Map(
    (digest?.groups || []).map((g) => [g.name, g] as const),
  );
  for (const [name, b] of map) {
    const dg = digestByName.get(name);
    if (dg?.lines?.length) b.digestLines = dg.lines.slice(0, 3);
  }
  // digest-only groups (beneficial hit but no recent activity in triage)
  for (const g of digest?.groups || []) {
    if (!map.has(g.name)) {
      map.set(g.name, {
        name: g.name,
        slug: g.slug || slugifyGroup(g.name),
        count: g.count || 0,
        latestAt: g.updated_at || null,
        lines: [],
        folder: null,
        digestLines: (g.lines || []).slice(0, 3),
      });
    }
  }

  return [...map.values()].sort((a, b) =>
    String(b.latestAt || "").localeCompare(String(a.latestAt || "")),
  );
}

export function yoritooriRelPath(groupName: string): string {
  return `815_神大家オプチャ/${groupName}/5.やり取り.md`;
}
