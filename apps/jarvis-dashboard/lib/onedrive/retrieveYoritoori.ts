/** OneDrive `5.やり取り.md` 末尾を ask 用に注入 */

import contacts from "@/config/partner_contacts.json";
import { findPartnerContact } from "@/lib/partnerContacts";
import {
  graphConfigured,
  partnerYoritooriRelPath,
  readOnedriveText,
} from "@/lib/onedrive/graphRead";

export type YoritooriRetrieveResult = {
  ok: boolean;
  promptBlock: string;
  notice: string;
  path?: string;
  chars?: number;
  via: "graph" | "unavailable" | "empty" | "no_folder";
  error?: string;
};

const MAX_TAIL = 7000;

type PartnerRow = { name: string; folder: string };

function clipTail(text: string, max = MAX_TAIL): string {
  const t = text.replace(/\r\n/g, "\n").trim();
  if (t.length <= max) return t;
  return `…（先頭省略）\n${t.slice(-max)}`;
}

/** payload / タイトルからパートナー folder を推定 */
export function resolvePartnerFolder(opts: {
  lane?: string | null;
  title?: string | null;
  summary?: string | null;
  payload?: Record<string, unknown> | null;
}): string | null {
  const payload = opts.payload || {};
  for (const key of ["folder", "partner_folder", "yoritoori_folder"] as const) {
    const v = payload[key];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  const partner =
    (typeof payload.partner === "string" && payload.partner) ||
    (typeof payload.partner_name === "string" && payload.partner_name) ||
    "";
  if (partner) {
    const c = findPartnerContact(partner, null);
    if (c?.folder) return c.folder;
  }

  const hay = [opts.title, opts.summary, partner]
    .filter(Boolean)
    .join("\n");
  if (!hay) return null;

  const list = (contacts as { partners: PartnerRow[] }).partners || [];
  // 長い folder / name を先に（部分一致の誤爆を減らす）
  const ranked = [...list].sort(
    (a, b) =>
      Math.max(b.folder.length, b.name.length) -
      Math.max(a.folder.length, a.name.length),
  );
  for (const c of ranked) {
    if (c.folder && hay.includes(c.folder)) return c.folder;
    if (c.name && hay.includes(c.name)) return c.folder;
  }
  // よくある略称（連絡先 JSON に無い管理会社）
  if (/Tcell|キャラメル/i.test(hay)) {
    return "103_Tcell";
  }
  if (/Grandole\s*[ⅠI1]/i.test(hay) || /志賀本通\s*[ⅠI1]/i.test(hay)) {
    const g = list.find((p) => /Grandole|志賀本通/i.test(p.folder + p.name));
    if (g) return g.folder;
  }
  return null;
}

export function defaultUseOnedriveYoritoori(
  lane: string | null | undefined,
): boolean {
  const l = (lane || "").toLowerCase();
  return (
    l === "partner" ||
    l === "properties" ||
    l === "openchat" ||
    l.includes("partner") ||
    l.includes("propert")
  );
}

function formatBlock(folder: string, relPath: string, tail: string): string {
  return [
    `【OneDrive やり取り末尾】（${folder}／読取のみ・Graph）`,
    `path: ${relPath}`,
    "",
    tail,
    "",
    "上記は正本の一部。無い事実は推測しない。",
  ].join("\n");
}

export async function retrieveYoritooriForAsk(opts: {
  lane?: string | null;
  title?: string | null;
  summary?: string | null;
  payload?: Record<string, unknown> | null;
  folderOverride?: string | null;
}): Promise<YoritooriRetrieveResult> {
  if (!graphConfigured()) {
    return {
      ok: false,
      promptBlock: "",
      notice:
        "OneDrive未配線（MS_GRAPH_CLIENT_ID / REFRESH_TOKEN）。聞く自体は続行",
      via: "unavailable",
    };
  }

  const folder =
    (opts.folderOverride || "").trim() ||
    resolvePartnerFolder({
      lane: opts.lane,
      title: opts.title,
      summary: opts.summary,
      payload: opts.payload,
    });
  if (!folder) {
    return {
      ok: false,
      promptBlock: "",
      notice: "OneDrive: パートナー folder を特定できずスキップ",
      via: "no_folder",
    };
  }

  const relPath = partnerYoritooriRelPath(folder);
  try {
    const text = await readOnedriveText(relPath);
    const tail = clipTail(text);
    if (!tail) {
      return {
        ok: true,
        promptBlock: "",
        notice: `OneDrive: ${folder} のやり取りが空`,
        path: relPath,
        chars: 0,
        via: "empty",
      };
    }
    return {
      ok: true,
      promptBlock: formatBlock(folder, relPath, tail),
      notice: `OneDriveやり取り末尾を参照: ${folder}（${tail.length}字）`,
      path: relPath,
      chars: tail.length,
      via: "graph",
    };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return {
      ok: false,
      promptBlock: "",
      notice: `OneDrive読取失敗（聞くは続行）: ${msg}`.slice(0, 160),
      path: relPath,
      via: "unavailable",
      error: msg,
    };
  }
}
