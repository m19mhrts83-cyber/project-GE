/**
 * 資料依頼の添付: OneDrive（個人用 215_神・大家さん倶楽部 配下）と
 * Google Drive（admin のマイドライブ）をファイル名で探し、選ばれたものを取得する。
 * どちらも既存の読取専用トークン（MS_GRAPH_* / GDRIVE_*）を使う。AI は使わない。
 */
import { gdriveConfigured, getGdriveAccessToken } from "@/lib/gdrive/driveRead";
import { getAccessToken as getGraphAccessToken, graphConfigured } from "@/lib/onedrive/graphRead";
import {
  MAX_ATTACH_BYTES,
  humanSize,
  rankCandidates,
  type MailAttachment,
  type MaterialCandidate,
  type MaterialSource,
} from "@/lib/materialFileSearch";

/** OneDrive 側の探索範囲（ドライブ直下からの相対パス） */
const ONEDRIVE_ROOT = (
  process.env.JARVIS_MATERIAL_ONEDRIVE_ROOT || "215_神・大家さん倶楽部"
).trim();

const PER_TERM = 15;

function graphDriveBase(): string {
  const driveId = (process.env.MS_GRAPH_DRIVE_ID || "").trim();
  const upn = (process.env.MS_GRAPH_USER_UPN || "").trim();
  if (driveId) return `https://graph.microsoft.com/v1.0/drives/${driveId}`;
  if (upn) return `https://graph.microsoft.com/v1.0/users/${encodeURIComponent(upn)}/drive`;
  return "https://graph.microsoft.com/v1.0/me/drive";
}

function encodePath(p: string): string {
  return p
    .replace(/^\/+|\/+$/g, "")
    .split("/")
    .map((s) => encodeURIComponent(s))
    .join("/");
}

async function searchOnedrive(token: string, term: string): Promise<MaterialCandidate[]> {
  const q = encodeURIComponent(term.replace(/'/g, "''"));
  const root = ONEDRIVE_ROOT ? `/root:/${encodePath(ONEDRIVE_ROOT)}:` : "/root";
  const url =
    `${graphDriveBase()}${root}/search(q='${q}')` +
    `?$top=${PER_TERM}&$select=id,name,size,file,lastModifiedDateTime`;
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new Error(`OneDrive 検索 HTTP ${res.status}`);
  const j = (await res.json()) as {
    value?: Array<{ id: string; name: string; size?: number; file?: unknown; lastModifiedDateTime?: string }>;
  };
  return (j.value || [])
    .filter((v) => v.file && v.id && v.name)
    .map((v) => ({ s: "od" as const, id: v.id, n: v.name, z: v.size, m: v.lastModifiedDateTime }));
}

async function searchGdrive(token: string, term: string): Promise<MaterialCandidate[]> {
  const e = term.replace(/\\/g, "\\\\").replace(/'/g, "\\'");
  const q =
    `name contains '${e}' and trashed = false and 'me' in owners ` +
    `and mimeType != 'application/vnd.google-apps.folder'`;
  const params = new URLSearchParams({
    q,
    pageSize: String(PER_TERM),
    orderBy: "modifiedTime desc",
    fields: "files(id,name,size,modifiedTime)",
  });
  const res = await fetch(`https://www.googleapis.com/drive/v3/files?${params}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`Google Drive 検索 HTTP ${res.status}`);
  const j = (await res.json()) as {
    files?: Array<{ id: string; name: string; size?: string; modifiedTime?: string }>;
  };
  return (j.files || []).map((f) => ({
    s: "gd" as const,
    id: f.id,
    n: f.name,
    z: f.size ? Number(f.size) : undefined,
    m: f.modifiedTime,
  }));
}

export type MaterialSearchResult = {
  candidates: MaterialCandidate[];
  /** 片方が使えなかったなどの注記 */
  notes: string[];
};

export async function searchMaterialFiles(terms: string[]): Promise<MaterialSearchResult> {
  const notes: string[] = [];
  if (!terms.length) return { candidates: [], notes: ["探す言葉がありません"] };
  const all: MaterialCandidate[] = [];

  const tasks: Promise<void>[] = [];
  if (graphConfigured()) {
    tasks.push(
      (async () => {
        const token = await getGraphAccessToken();
        const lists = await Promise.all(terms.map((t) => searchOnedrive(token, t).catch(() => [])));
        all.push(...lists.flat());
      })().catch((e) => {
        notes.push(`OneDrive を探せませんでした（${e instanceof Error ? e.message : e}）`);
      }),
    );
  } else {
    notes.push("OneDrive の接続設定がありません");
  }
  if (gdriveConfigured()) {
    tasks.push(
      (async () => {
        const token = await getGdriveAccessToken();
        const lists = await Promise.all(terms.map((t) => searchGdrive(token, t).catch(() => [])));
        all.push(...lists.flat());
      })().catch((e) => {
        notes.push(`Google Drive を探せませんでした（${e instanceof Error ? e.message : e}）`);
      }),
    );
  } else {
    notes.push("Google Drive の接続設定がありません");
  }
  await Promise.all(tasks);
  return { candidates: rankCandidates(all, terms, 10), notes };
}

const GOOGLE_EXPORT: Record<string, { mime: string; ext: string }> = {
  "application/vnd.google-apps.document": { mime: "application/pdf", ext: ".pdf" },
  "application/vnd.google-apps.spreadsheet": { mime: "application/pdf", ext: ".pdf" },
  "application/vnd.google-apps.presentation": { mime: "application/pdf", ext: ".pdf" },
  "application/vnd.google-apps.drawing": { mime: "application/pdf", ext: ".pdf" },
};

async function downloadOnedrive(token: string, id: string): Promise<MailAttachment> {
  const metaRes = await fetch(
    `${graphDriveBase()}/items/${encodeURIComponent(id)}?$select=name,size,file,@microsoft.graph.downloadUrl`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (!metaRes.ok) throw new Error(`OneDrive ファイル情報 HTTP ${metaRes.status}`);
  const meta = (await metaRes.json()) as {
    name?: string;
    size?: number;
    file?: { mimeType?: string };
    "@microsoft.graph.downloadUrl"?: string;
  };
  if ((meta.size || 0) > MAX_ATTACH_BYTES) {
    throw new Error(`${meta.name} が大きすぎます（${humanSize(meta.size)}）`);
  }
  const dl = meta["@microsoft.graph.downloadUrl"];
  if (!dl) throw new Error(`${meta.name || id} をダウンロードできません`);
  const res = await fetch(dl);
  if (!res.ok) throw new Error(`OneDrive ダウンロード HTTP ${res.status}`);
  return {
    filename: meta.name || "file",
    mimeType: meta.file?.mimeType || "application/octet-stream",
    data: Buffer.from(await res.arrayBuffer()),
  };
}

async function downloadGdrive(token: string, id: string): Promise<MailAttachment> {
  const auth = { Authorization: `Bearer ${token}` };
  const metaRes = await fetch(
    `https://www.googleapis.com/drive/v3/files/${encodeURIComponent(id)}?fields=name,mimeType,size`,
    { headers: auth },
  );
  if (!metaRes.ok) throw new Error(`Google Drive ファイル情報 HTTP ${metaRes.status}`);
  const meta = (await metaRes.json()) as { name?: string; mimeType?: string; size?: string };
  if (Number(meta.size || 0) > MAX_ATTACH_BYTES) {
    throw new Error(`${meta.name} が大きすぎます（${humanSize(Number(meta.size))}）`);
  }
  const exp = GOOGLE_EXPORT[meta.mimeType || ""];
  const url = exp
    ? `https://www.googleapis.com/drive/v3/files/${encodeURIComponent(id)}/export?mimeType=${encodeURIComponent(exp.mime)}`
    : `https://www.googleapis.com/drive/v3/files/${encodeURIComponent(id)}?alt=media`;
  const res = await fetch(url, { headers: auth });
  if (!res.ok) throw new Error(`Google Drive ダウンロード HTTP ${res.status}（${meta.name}）`);
  const name = meta.name || "file";
  return {
    filename: exp && !name.toLowerCase().endsWith(exp.ext) ? `${name}${exp.ext}` : name,
    mimeType: exp?.mime || meta.mimeType || "application/octet-stream",
    data: Buffer.from(await res.arrayBuffer()),
  };
}

/** 選ばれた候補を取得。合計が上限を超えたらエラー。 */
export async function downloadMaterialFiles(
  refs: Array<{ s: MaterialSource; id: string }>,
): Promise<MailAttachment[]> {
  if (!refs.length) return [];
  const needOd = refs.some((r) => r.s === "od");
  const needGd = refs.some((r) => r.s === "gd");
  const [odToken, gdToken] = await Promise.all([
    needOd ? getGraphAccessToken() : Promise.resolve(""),
    needGd ? getGdriveAccessToken() : Promise.resolve(""),
  ]);
  const files = await Promise.all(
    refs.map((r) => (r.s === "od" ? downloadOnedrive(odToken, r.id) : downloadGdrive(gdToken, r.id))),
  );
  const total = files.reduce((n, f) => n + f.data.length, 0);
  if (total > MAX_ATTACH_BYTES) {
    throw new Error(`添付の合計が大きすぎます（${humanSize(total)}、上限 ${humanSize(MAX_ATTACH_BYTES)}）`);
  }
  return files;
}
