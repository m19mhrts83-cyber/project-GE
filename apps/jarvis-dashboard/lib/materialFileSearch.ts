/**
 * 資料依頼の添付候補探し・添付付きメール組み立て（通信なしの純粋関数）。
 * 通信は lib/materialFiles.ts。
 */

export type MaterialSource = "od" | "gd";

export type MaterialCandidate = {
  /** od = OneDrive（個人用）, gd = Google Drive（admin） */
  s: MaterialSource;
  id: string;
  /** ファイル名 */
  n: string;
  /** 更新日時 ISO（並び替え用） */
  m?: string;
  /** バイト数（Google ドキュメント類は未定） */
  z?: number;
};

export type MailAttachment = {
  filename: string;
  mimeType: string;
  data: Buffer;
};

/** 品目から外す語（ファイル名に出にくい） */
const TRIM_SUFFIX_RE =
  /(の)?(写し|コピー|原本|PDF|pdf|データ|ファイル|一式|等|など|のご提出|のご送付|をお願い.*|をご.*|について.*)$/;
const PAREN_RE = /[（(【\[「『][^）)】\]」』]*[）)】\]」』]/g;
const SPLIT_RE = /[、,・／/\s]+|の/;
/** 単独では広すぎる語 */
const STOP_TERMS = new Set([
  "資料", "書類", "書面", "最新", "直近", "今期", "前期", "全て", "すべて", "必要", "各種", "提出",
]);

function cleanItem(item: string): string {
  let s = String(item || "")
    .replace(PAREN_RE, " ")
    .replace(/^[\s・•\-*0-9０-９.．)）①-⑳]+/, "")
    .trim();
  for (let i = 0; i < 3; i++) {
    const next = s.replace(TRIM_SUFFIX_RE, "").trim();
    if (next === s) break;
    s = next;
  }
  return s;
}

/**
 * 依頼品目（と任意の検索語）からファイル名検索の語を作る。
 * 品目そのもの → 長ければ「の」「・」などで分けた語、の順。最大 maxTerms 語。
 */
export function searchTermsFromItems(
  items: string[],
  extra?: string,
  maxTerms = 6,
): string[] {
  const out: string[] = [];
  const push = (t: string) => {
    const v = t.trim();
    if (v.length < 2 || v.length > 30 || STOP_TERMS.has(v)) return;
    if (!out.includes(v)) out.push(v);
  };
  for (const raw of String(extra || "").split(/[、,\s]+/)) push(raw);
  for (const item of items) {
    const c = cleanItem(item);
    if (!c) continue;
    if (c.length <= 12) push(c);
    for (const part of c.split(SPLIT_RE)) push(cleanItem(part));
  }
  return out.slice(0, maxTerms);
}

function norm(s: string): string {
  return s.normalize("NFKC").toLowerCase();
}

/** 当たった語の数 → 更新が新しい順。同じ (s,id) は1件に。 */
export function rankCandidates(
  cands: MaterialCandidate[],
  terms: string[],
  limit = 10,
): MaterialCandidate[] {
  const seen = new Set<string>();
  const scored: Array<{ c: MaterialCandidate; score: number }> = [];
  const nterms = terms.map(norm);
  for (const c of cands) {
    const key = `${c.s}:${c.id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const name = norm(c.n);
    const score = nterms.filter((t) => name.includes(t)).length;
    scored.push({ c, score });
  }
  scored.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    return String(b.c.m || "").localeCompare(String(a.c.m || ""));
  });
  return scored.slice(0, limit).map((x) => x.c);
}

/** Slack の選択肢 value（150字まで）: od:{id} / gd:{id} */
export function candidateValue(c: Pick<MaterialCandidate, "s" | "id">): string {
  return `${c.s}:${c.id}`;
}

export function parseCandidateValue(v: string): { s: MaterialSource; id: string } | null {
  const m = String(v || "").match(/^(od|gd):([A-Za-z0-9!_.\-]{4,140})$/);
  return m ? { s: m[1] as MaterialSource, id: m[2] } : null;
}

export function humanSize(bytes?: number): string {
  if (!bytes || bytes <= 0) return "";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))}KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

/** Gmail の上限（25MB）に base64 の膨らみを見込んだ添付合計の上限 */
export const MAX_ATTACH_BYTES = 18 * 1024 * 1024;

function b64Header(v: string): string {
  if (!/[^\x00-\x7F]/.test(v)) return v;
  return `=?UTF-8?B?${Buffer.from(v, "utf8").toString("base64")}?=`;
}

function wrap76(b64: string): string {
  return b64.replace(/.{1,76}/g, (x) => `${x}\r\n`).trimEnd();
}

/** Gmail API raw 用の MIME 本文（添付なしなら text/plain 1パート） */
export function buildMimeMessage(opts: {
  to: string;
  subject: string;
  body: string;
  attachments?: MailAttachment[];
  boundary?: string;
}): string {
  const head = [
    `To: ${opts.to}`,
    `Subject: ${b64Header(opts.subject)}`,
    "MIME-Version: 1.0",
  ];
  const atts = opts.attachments || [];
  if (!atts.length) {
    return [...head, "Content-Type: text/plain; charset=UTF-8", "", opts.body].join("\r\n");
  }
  const boundary = opts.boundary || `jarvis_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
  const lines = [
    ...head,
    `Content-Type: multipart/mixed; boundary="${boundary}"`,
    "",
    `--${boundary}`,
    "Content-Type: text/plain; charset=UTF-8",
    "Content-Transfer-Encoding: base64",
    "",
    wrap76(Buffer.from(opts.body, "utf8").toString("base64")),
  ];
  for (const a of atts) {
    const name = a.filename.replace(/["\r\n]/g, "_");
    const enc = b64Header(name);
    lines.push(
      `--${boundary}`,
      `Content-Type: ${a.mimeType || "application/octet-stream"}; name="${enc}"`,
      `Content-Disposition: attachment; filename="${enc}"; filename*=UTF-8''${encodeURIComponent(name)}`,
      "Content-Transfer-Encoding: base64",
      "",
      wrap76(a.data.toString("base64")),
    );
  }
  lines.push(`--${boundary}--`, "");
  return lines.join("\r\n");
}
