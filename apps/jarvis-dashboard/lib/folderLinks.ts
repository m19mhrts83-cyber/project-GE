/** 詳細ページ用 OneDrive / Google Drive リンク（手動マッピング） */

import raw from "@/data/folder_links.json";
import { findPartnerContact } from "@/lib/partnerContacts";

export type FolderLinkKind = "onedrive" | "gdrive" | "other";

export type FolderLink = {
  label: string;
  url: string;
  kind: FolderLinkKind;
};

type FolderLinksFile = {
  version?: number;
  links?: Record<string, FolderLink[]>;
};

const DATA = raw as FolderLinksFile;

export function getFolderLinks(key: string | null | undefined): FolderLink[] {
  if (!key) return [];
  const rows = DATA.links?.[key] || [];
  return rows.filter(
    (r) =>
      r &&
      typeof r.url === "string" &&
      r.url.trim().startsWith("http") &&
      typeof r.label === "string" &&
      r.label.trim(),
  );
}

/** 複数キーを順にマージ（重複 URL は除外） */
export function getFolderLinksMany(
  keys: Array<string | null | undefined>,
): FolderLink[] {
  const seen = new Set<string>();
  const out: FolderLink[] = [];
  for (const key of keys) {
    for (const link of getFolderLinks(key)) {
      if (seen.has(link.url)) continue;
      seen.add(link.url);
      out.push(link);
    }
  }
  return out;
}

export function partnerFolderKey(
  folder?: string | null,
  partner?: string | null,
): string | null {
  const f = (folder || "").trim();
  if (f) return `partner:${f}`;
  const c = findPartnerContact(partner, null);
  if (c?.folder) return `partner:${c.folder}`;
  return null;
}

export function laneFolderKey(lane: string): string {
  // ai-raimo ページの lane id は ai_raimo
  const id = lane === "ai-raimo" ? "ai_raimo" : lane;
  return `lane:${id}`;
}

export function pageFolderKey(pageId: string): string {
  return `page:${pageId}`;
}

export function openchatFolderKey(groupName: string): string {
  return `openchat:${groupName.trim()}`;
}
