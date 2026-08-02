/**
 * Microsoft Graph（委任 refresh）で OneDrive ファイルを読む。
 * refresh が回転したら sync_meta に保存（次回以降の Vercel 用）。
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const REFRESH_META_KEY = "ms_graph_refresh_token";
const PARTNER_ROOT =
  "215_神・大家さん倶楽部/C2_ルーティン作業/26_パートナー社への相談";

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

export function graphConfigured(): boolean {
  return Boolean(
    (process.env.MS_GRAPH_CLIENT_ID || "").trim() &&
      (process.env.MS_GRAPH_REFRESH_TOKEN || "").trim(),
  );
}

export function partnerYoritooriRelPath(folder: string): string {
  const f = folder.replace(/^\/+|\/+$/g, "");
  return `${PARTNER_ROOT}/${f}/5.やり取り.md`;
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

async function getAccessToken(): Promise<string> {
  const clientId = (process.env.MS_GRAPH_CLIENT_ID || "").trim();
  const authority = (process.env.MS_GRAPH_AUTHORITY || "consumers").trim();
  let refresh =
    (await loadPersistedRefresh()) ||
    (process.env.MS_GRAPH_REFRESH_TOKEN || "").trim();
  if (!clientId || !refresh) {
    throw new Error("MS_GRAPH_CLIENT_ID / MS_GRAPH_REFRESH_TOKEN 未設定");
  }

  const body = new URLSearchParams({
    client_id: clientId,
    grant_type: "refresh_token",
    refresh_token: refresh,
    scope: "offline_access Files.Read Files.Read.All User.Read",
  });
  const secret = (process.env.MS_GRAPH_CLIENT_SECRET || "").trim();
  if (secret) body.set("client_secret", secret);

  const res = await fetch(
    `https://login.microsoftonline.com/${authority}/oauth2/v2.0/token`,
    {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    },
  );
  if (!res.ok) {
    const detail = (await res.text()).slice(0, 240);
    throw new Error(`Graph token HTTP ${res.status}: ${detail}`);
  }
  const json = (await res.json()) as {
    access_token?: string;
    refresh_token?: string;
  };
  if (!json.access_token) throw new Error("Graph access_token なし");
  if (json.refresh_token && json.refresh_token !== refresh) {
    process.env.MS_GRAPH_REFRESH_TOKEN = json.refresh_token;
    await persistRefresh(json.refresh_token);
  }
  return json.access_token;
}

function encodeDrivePath(relPath: string): string {
  return relPath
    .replace(/^\/+|\/+$/g, "")
    .split("/")
    .map((seg) => encodeURIComponent(seg))
    .join("/");
}

function itemMetaUrl(relPath: string): string {
  const driveId = (process.env.MS_GRAPH_DRIVE_ID || "").trim();
  const upn = (process.env.MS_GRAPH_USER_UPN || "").trim();
  const encoded = encodeDrivePath(relPath);
  if (driveId) {
    return `https://graph.microsoft.com/v1.0/drives/${driveId}/root:/${encoded}`;
  }
  if (upn) {
    return `https://graph.microsoft.com/v1.0/users/${encodeURIComponent(upn)}/drive/root:/${encoded}`;
  }
  return `https://graph.microsoft.com/v1.0/me/drive/root:/${encoded}`;
}

/** Graph downloadUrl 経由でファイル本文を取得 */
export async function readOnedriveText(relPath: string): Promise<string> {
  const token = await getAccessToken();
  const metaUrl =
    itemMetaUrl(relPath) + "?$select=id,name,size,@microsoft.graph.downloadUrl";
  const metaRes = await fetch(metaUrl, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!metaRes.ok) {
    const detail = (await metaRes.text()).slice(0, 240);
    throw new Error(`Graph meta HTTP ${metaRes.status}: ${detail}`);
  }
  const meta = (await metaRes.json()) as {
    "@microsoft.graph.downloadUrl"?: string;
  };
  const downloadUrl = meta["@microsoft.graph.downloadUrl"] || "";
  if (!downloadUrl) {
    throw new Error("Graph downloadUrl なし");
  }
  // pre-authenticated CDN — Bearer を付けない
  const fileRes = await fetch(downloadUrl);
  if (!fileRes.ok) {
    throw new Error(`Graph download HTTP ${fileRes.status}`);
  }
  return await fileRes.text();
}
