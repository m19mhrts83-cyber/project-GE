/**
 * Google Drive（admin・drive.readonly）読取。
 * refresh が回転したら sync_meta に保存（Vercel 次回用）。
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const REFRESH_META_KEY = "gdrive_refresh_token";

function jarvisAdminOrNull(): SupabaseClient | null {
  const url = (process.env.JARVIS_SUPABASE_URL || "").trim();
  const key = (
    process.env.JARVIS_SUPABASE_SECRET_KEY ||
    process.env.JARVIS_SUPABASE_SERVICE_ROLE_KEY ||
    ""
  ).trim();
  if (!url || !key) return null;
  return createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

export function gdriveConfigured(): boolean {
  return Boolean(
    (process.env.GDRIVE_CLIENT_ID || "").trim() &&
      (process.env.GDRIVE_CLIENT_SECRET || "").trim() &&
      (process.env.GDRIVE_REFRESH_TOKEN || "").trim(),
  );
}

export function notebookLmFolderId(): string {
  const fromEnv = (process.env.GDRIVE_NOTEBOOKLM_FOLDER_ID || "").trim();
  if (fromEnv) return fromEnv;
  const url = (process.env.NOTEBOOKLM_DRIVE_FOLDER_URL || "").trim();
  const m = url.match(/\/folders\/([a-zA-Z0-9_-]+)/);
  return m?.[1] || "";
}

async function loadPersistedRefresh(): Promise<string> {
  const sb = jarvisAdminOrNull();
  if (!sb) return "";
  try {
    const { data } = await sb
      .from("sync_meta")
      .select("value")
      .eq("key", REFRESH_META_KEY)
      .maybeSingle();
    const v = data?.value;
    return typeof v === "string" ? v.trim() : "";
  } catch {
    return "";
  }
}

async function persistRefresh(token: string): Promise<void> {
  const sb = jarvisAdminOrNull();
  if (!sb || !token) return;
  try {
    await sb.from("sync_meta").upsert(
      {
        key: REFRESH_META_KEY,
        value: token,
        updated_at: new Date().toISOString(),
      },
      { onConflict: "key" },
    );
  } catch {
    /* best-effort */
  }
}

export async function getGdriveAccessToken(): Promise<string> {
  const clientId = (process.env.GDRIVE_CLIENT_ID || "").trim();
  const clientSecret = (process.env.GDRIVE_CLIENT_SECRET || "").trim();
  let refresh =
    (await loadPersistedRefresh()) ||
    (process.env.GDRIVE_REFRESH_TOKEN || "").trim();
  if (!clientId || !clientSecret || !refresh) {
    throw new Error("GDRIVE_CLIENT_ID / SECRET / REFRESH_TOKEN 未設定");
  }

  const body = new URLSearchParams({
    client_id: clientId,
    client_secret: clientSecret,
    grant_type: "refresh_token",
    refresh_token: refresh,
  });
  const res = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) {
    const detail = (await res.text()).slice(0, 240);
    throw new Error(`GDrive token HTTP ${res.status}: ${detail}`);
  }
  const json = (await res.json()) as {
    access_token?: string;
    refresh_token?: string;
  };
  if (!json.access_token) throw new Error("GDrive access_token なし");
  if (json.refresh_token && json.refresh_token !== refresh) {
    process.env.GDRIVE_REFRESH_TOKEN = json.refresh_token;
    await persistRefresh(json.refresh_token);
  }
  return json.access_token;
}

export type DriveFileMeta = {
  id: string;
  name: string;
  mimeType: string;
  parents?: string[];
};

function escapeDriveQuery(s: string): string {
  return s.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
}

/** fullText / name 検索（trashed 除外）。フォルダ配下の絞り込みは呼び出し側。 */
export async function searchDriveFiles(
  accessToken: string,
  queryText: string,
  opts?: { pageSize?: number },
): Promise<DriveFileMeta[]> {
  const terms = queryText
    .replace(/[^\p{L}\p{N}\s_-]/gu, " ")
    .split(/\s+/)
    .map((t) => t.trim())
    .filter((t) => t.length >= 2)
    .slice(0, 4);
  if (!terms.length) return [];

  const clauses = terms.map((t) => {
    const e = escapeDriveQuery(t);
    return `(fullText contains '${e}' or name contains '${e}')`;
  });
  const q = `(${clauses.join(" or ")}) and trashed = false and mimeType != 'application/vnd.google-apps.folder'`;
  const params = new URLSearchParams({
    q,
    spaces: "drive",
    pageSize: String(opts?.pageSize ?? 12),
    fields: "files(id,name,mimeType,parents)",
  });
  const res = await fetch(
    `https://www.googleapis.com/drive/v3/files?${params}`,
    {
      headers: { Authorization: `Bearer ${accessToken}` },
      next: { revalidate: 0 },
    },
  );
  if (!res.ok) {
    const detail = (await res.text()).slice(0, 200);
    throw new Error(`Drive search HTTP ${res.status}: ${detail}`);
  }
  const json = (await res.json()) as { files?: DriveFileMeta[] };
  return json.files || [];
}

const parentCache = new Map<string, string[]>();

async function getParents(
  accessToken: string,
  fileId: string,
): Promise<string[]> {
  const cached = parentCache.get(fileId);
  if (cached) return cached;
  const res = await fetch(
    `https://www.googleapis.com/drive/v3/files/${encodeURIComponent(fileId)}?fields=parents`,
    {
      headers: { Authorization: `Bearer ${accessToken}` },
      next: { revalidate: 0 },
    },
  );
  if (!res.ok) {
    parentCache.set(fileId, []);
    return [];
  }
  const json = (await res.json()) as { parents?: string[] };
  const parents = json.parents || [];
  parentCache.set(fileId, parents);
  return parents;
}

/** rootFolderId 配下（子孫）か。祖先を辿る。 */
export async function isUnderFolder(
  accessToken: string,
  fileId: string,
  rootFolderId: string,
  opts?: { maxDepth?: number },
): Promise<boolean> {
  if (!rootFolderId) return true;
  const maxDepth = opts?.maxDepth ?? 12;
  let current = fileId;
  const seen = new Set<string>();
  for (let i = 0; i < maxDepth; i++) {
    if (current === rootFolderId) return true;
    if (seen.has(current)) return false;
    seen.add(current);
    const parents = await getParents(accessToken, current);
    if (!parents.length) return false;
    if (parents.includes(rootFolderId)) return true;
    current = parents[0];
  }
  return false;
}

export async function readDriveFileText(
  accessToken: string,
  file: DriveFileMeta,
  maxChars = 4000,
): Promise<string> {
  const mime = file.mimeType || "";
  let url: string;
  if (mime === "application/vnd.google-apps.document") {
    url = `https://www.googleapis.com/drive/v3/files/${encodeURIComponent(file.id)}/export?mimeType=${encodeURIComponent("text/plain")}`;
  } else if (
    mime.startsWith("text/") ||
    mime === "application/json" ||
    /\.(md|txt|markdown)$/i.test(file.name)
  ) {
    url = `https://www.googleapis.com/drive/v3/files/${encodeURIComponent(file.id)}?alt=media`;
  } else {
    return "";
  }

  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${accessToken}` },
    next: { revalidate: 0 },
  });
  if (!res.ok) return "";
  const text = (await res.text()).replace(/\r\n/g, "\n").trim();
  if (text.length <= maxChars) return text;
  return `…（先頭省略）\n${text.slice(-maxChars)}`;
}
