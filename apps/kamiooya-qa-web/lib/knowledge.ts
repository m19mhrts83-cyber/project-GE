import { readFile } from "node:fs/promises";
import { join } from "node:path";

export type KnowledgeRow = {
  commentId: string;
  postedAt?: string;
  authorName?: string;
  sourceType?: string;
  content: string;
};

export type KnowledgeHit = KnowledgeRow & {
  score: number;
  snippet: string;
};

function normalize(s: string): string {
  return String(s || "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

function tokenize(q: string): string[] {
  const s = normalize(q);
  if (!s) return [];
  return Array.from(new Set(s.split(/[^0-9a-zA-Zぁ-んァ-ン一-龥]+/).filter(Boolean)));
}

function parseCsvLine(line: string, delimiter: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inQuote = false;
  for (let i = 0; i < line.length; i += 1) {
    const c = line[i];
    if (c === '"' && inQuote && line[i + 1] === '"') {
      cur += '"';
      i += 1;
      continue;
    }
    if (c === '"') {
      inQuote = !inQuote;
      continue;
    }
    if (!inQuote && c === delimiter) {
      out.push(cur);
      cur = "";
      continue;
    }
    cur += c;
  }
  out.push(cur);
  return out;
}

function splitRecords(text: string): string[] {
  const normalized = String(text || "").replace(/^\uFEFF/, "").replace(/\r/g, "");
  const records: string[] = [];
  let buf = "";
  let inQuote = false;
  for (let i = 0; i < normalized.length; i += 1) {
    const c = normalized[i];
    if (c === '"' && inQuote && normalized[i + 1] === '"') {
      buf += '"';
      i += 1;
      continue;
    }
    if (c === '"') {
      inQuote = !inQuote;
      buf += c;
      continue;
    }
    if (c === "\n" && !inQuote) {
      if (buf.trim() !== "") records.push(buf);
      buf = "";
      continue;
    }
    buf += c;
  }
  if (buf.trim() !== "") records.push(buf);
  return records;
}

function detectDelimiter(headerLine: string): string {
  const count = (ch: string) => {
    let n = 0;
    let inQuote = false;
    for (let i = 0; i < headerLine.length; i += 1) {
      const c = headerLine[i];
      if (c === '"' && inQuote && headerLine[i + 1] === '"') {
        i += 1;
        continue;
      }
      if (c === '"') {
        inQuote = !inQuote;
        continue;
      }
      if (!inQuote && c === ch) n += 1;
    }
    return n;
  };
  const tab = count("\t");
  const semi = count(";");
  const comma = count(",");
  if (tab >= semi && tab >= comma && tab > 0) return "\t";
  if (semi > comma) return ";";
  return ",";
}

function getCell(row: Record<string, string>, ...keys: string[]): string {
  for (const k of keys) {
    if (Object.prototype.hasOwnProperty.call(row, k)) {
      const v = String(row[k] ?? "").trim();
      if (v) return v;
    }
  }
  return "";
}

export async function loadKnowledge(): Promise<KnowledgeRow[]> {
  // デプロイ時はリポジトリに同梱した data/knowledge.csv を読む想定
  const p = join(process.cwd(), "data", "knowledge.csv");
  const text = await readFile(p, "utf-8");
  const records = splitRecords(text);
  if (records.length <= 1) return [];
  const delimiter = detectDelimiter(records[0]);
  const headers = parseCsvLine(records[0], delimiter).map((h) => h.replace(/^\uFEFF/, "").trim());

  const rows: KnowledgeRow[] = [];
  for (let i = 1; i < records.length; i += 1) {
    const values = parseCsvLine(records[i], delimiter);
    const row: Record<string, string> = {};
    headers.forEach((h, idx) => {
      row[h] = values[idx] ?? "";
    });

    const content = getCell(row, "コメント内容", "content", "本文", "Content");
    const commentId =
      getCell(row, "コメントID", "comment_id", "commentId") || `row-${i}`;
    if (!content.trim()) continue;

    rows.push({
      commentId: String(commentId).trim(),
      postedAt: getCell(row, "投稿日時", "posted_at", "postedAt", "日時"),
      authorName: getCell(row, "投稿者名", "author_name", "authorName", "投稿者", "author"),
      sourceType: getCell(row, "ソース", "source_type", "sourceType", "データソース"),
      content: content
    });
  }
  return rows;
}

export function searchKnowledge(rows: KnowledgeRow[], query: string, limit = 8): KnowledgeHit[] {
  const terms = tokenize(query);
  if (terms.length === 0) return [];

  const hits: KnowledgeHit[] = [];
  for (const r of rows) {
    const hay = normalize([r.sourceType, r.authorName, r.postedAt, r.content].filter(Boolean).join(" "));
    let score = 0;
    for (const t of terms) {
      if (!t) continue;
      const idx = hay.indexOf(t);
      if (idx !== -1) score += 10;
    }
    if (score <= 0) continue;

    const raw = String(r.content || "");
    const q0 = terms[0] ?? "";
    const i0 = q0 ? normalize(raw).indexOf(q0) : -1;
    const start = Math.max(0, (i0 === -1 ? 0 : i0) - 60);
    const snippet = raw.slice(start, start + 220).replace(/\s+/g, " ").trim();

    hits.push({ ...r, score, snippet });
  }

  hits.sort((a, b) => b.score - a.score);
  return hits.slice(0, limit);
}

