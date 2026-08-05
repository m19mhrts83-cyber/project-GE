/** admin Drive `200_NoteBookLM` を ask 用に検索・注入 */

import {
  gdriveConfigured,
  getGdriveAccessToken,
  isUnderFolder,
  notebookLmFolderId,
  readDriveFileText,
  searchDriveFiles,
  type DriveFileMeta,
} from "@/lib/gdrive/driveRead";

export type NotebookLmRetrieveResult = {
  ok: boolean;
  promptBlock: string;
  notice: string;
  hits: number;
  via: "gdrive" | "unavailable" | "empty" | "no_query";
  error?: string;
};

const MAX_HITS = 4;
const MAX_CHARS_PER = 2800;
const MAX_TOTAL = 7000;

const PREFERRED_MIME = new Set([
  "application/vnd.google-apps.document",
  "text/plain",
  "text/markdown",
  "text/x-markdown",
  "application/json",
]);

function scoreFile(f: DriveFileMeta): number {
  let s = 0;
  if (PREFERRED_MIME.has(f.mimeType)) s += 10;
  if (/\.(md|txt|markdown)$/i.test(f.name)) s += 8;
  if (/pdf|image|video|audio|zip|pptx|xlsx/i.test(f.mimeType + f.name)) s -= 20;
  return s;
}

export async function retrieveNotebookLmForAsk(
  query: string,
): Promise<NotebookLmRetrieveResult> {
  const q = (query || "").trim();
  if (!q) {
    return {
      ok: false,
      promptBlock: "",
      notice: "Drive／NotebookLM: 検索語なし",
      hits: 0,
      via: "no_query",
    };
  }
  if (!gdriveConfigured()) {
    return {
      ok: false,
      promptBlock: "",
      notice:
        "Drive／NotebookLM: GDRIVE_* 未設定（scripts/jarvis_gdrive_admin_login.py）",
      hits: 0,
      via: "unavailable",
    };
  }

  try {
    const token = await getGdriveAccessToken();
    const folderId = notebookLmFolderId();
    const found = await searchDriveFiles(token, q, { pageSize: 16 });
    const under: DriveFileMeta[] = [];
    for (const f of found) {
      if (scoreFile(f) < 0) continue;
      const ok = folderId
        ? await isUnderFolder(token, f.id, folderId)
        : true;
      if (ok) under.push(f);
      if (under.length >= MAX_HITS * 2) break;
    }
    under.sort((a, b) => scoreFile(b) - scoreFile(a));
    const picked = under.slice(0, MAX_HITS);

    if (!picked.length) {
      return {
        ok: true,
        promptBlock: "",
        notice: folderId
          ? `Drive／NotebookLM: ヒット0（folder=${folderId.slice(0, 8)}…）`
          : "Drive／NotebookLM: ヒット0（FOLDER_ID 未設定・全体検索）",
        hits: 0,
        via: "empty",
      };
    }

    const chunks: string[] = [];
    let total = 0;
    let used = 0;
    for (const f of picked) {
      const body = await readDriveFileText(token, f, MAX_CHARS_PER);
      if (!body) continue;
      const block = `### ${f.name}\n${body}`;
      if (total + block.length > MAX_TOTAL && chunks.length) break;
      chunks.push(block);
      total += block.length;
      used += 1;
    }

    if (!chunks.length) {
      return {
        ok: true,
        promptBlock: "",
        notice: `Drive／NotebookLM: ${picked.length}件はあったがテキスト抽出0（PDF等は未対応）`,
        hits: 0,
        via: "empty",
      };
    }

    const promptBlock = [
      "## Google Drive／NotebookLM（200_NoteBookLM・要約スニペット）",
      "以下は ask 用の抜粋。推測で補完しない。",
      ...chunks,
    ].join("\n\n");

    return {
      ok: true,
      promptBlock,
      notice: `Drive／NotebookLM: ${used}件注入`,
      hits: used,
      via: "gdrive",
    };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return {
      ok: false,
      promptBlock: "",
      notice: `Drive／NotebookLM: 失敗（${msg.slice(0, 120)}）`,
      hits: 0,
      via: "unavailable",
      error: msg,
    };
  }
}
