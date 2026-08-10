/** グルコン下書きの投稿可否（成果なし・skipped の誤投稿防止） */

import type { GluconReportKind } from "./types";

export function isNoResultBody(body: string): boolean {
  const t = (body || "").trim();
  if (!t) return true;
  if (t.includes("該当する成果報告なし")) return true;
  // 短い「なし」系（生成揺れ）
  if (t.length < 40 && /成果報告なし|報告なし|該当なし|成果なし/.test(t)) {
    return true;
  }
  return false;
}

export function resolveDraftSaveStatus(args: {
  kind: GluconReportKind;
  body: string;
  existingStatus?: string | null;
}): "ready" | "skipped" | "queued" {
  const { kind, body, existingStatus } = args;
  if (existingStatus === "queued") return "queued";
  if (kind === "result" && isNoResultBody(body)) return "skipped";
  return "ready";
}

export function queueBlockReason(args: {
  kind: GluconReportKind;
  body: string;
  status?: string | null;
}): string | null {
  const { kind, body, status } = args;
  if (!String(body || "").trim()) return "本文が空です";
  if (kind === "result" && isNoResultBody(body)) {
    return "「該当する成果報告なし」など空の成果は投稿対象外です。投稿スキップのままで問題ありません。";
  }
  if (status === "posted") {
    return "既に投稿済みです。再投稿する場合は本文を保存し直してください。";
  }
  if (status === "queued") {
    return "既に投稿待ちです。Mac worker の完了を待ってください。";
  }
  if (status === "skipped") {
    return "スキップ済みです。実内容に書き換えて保存してから投稿してください。";
  }
  return null;
}

export function canQueueGluconDraft(args: {
  kind: GluconReportKind;
  body: string;
  status?: string | null;
}): boolean {
  return queueBlockReason(args) === null;
}
