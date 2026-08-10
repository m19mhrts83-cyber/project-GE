/** OneDrive 5.やり取り.md から期間内の不動産関連やり取りを抜粋 */

import sources from "@/data/glucon_sources.json";
import {
  graphConfigured,
  partnerYoritooriRelPath,
  readOnedriveText,
} from "@/lib/onedrive/graphRead";

export type YoritooriDigestLine = {
  date: string;
  partner: string;
  folder: string;
  direction: string;
  subject: string;
  keywords: string[];
};

export type YoritooriDigestResult = {
  ok: boolean;
  from: string;
  to: string;
  lines: YoritooriDigestLine[];
  notices: string[];
  skipped: string[];
};

type PartnerCfg = { folder: string; name: string };

const KEYWORD_RE =
  /神大家|神尾屋|WeStudy|グルコン|物件|融資|空室|戸建|アパート|LEAF|ミニテック|Raimo|AI推進|購入相談|管理会社|利回り|修繕|インベース|買付|決済|賃料|大家|オリックス|滋賀銀行|公庫|退去|入居|原状回復|契約|電子署名|スマートロック|セサミ|Grandole|志賀本通/i;

const EXCLUDE_RE =
  /人員計画|採用枠|人事部|工数計上|防衛省|コンプライアンス監査|社内DX|評価面談|1on1|ワンオンワン|組織改編|異動発令/i;

const HEADING_RE =
  /^###\s+(\d{4})\/(\d{2})\/(\d{2})(?:\s+\d{1,2}:\d{2})?｜([^｜]+)｜([^｜]+)｜(.*)$/;

const SUBJECT_RE = /^\*\*件名\*\*:\s*(.+)$/m;

function loadPartners(): PartnerCfg[] {
  const list = (sources as { yoritoori_partners?: PartnerCfg[] })
    .yoritoori_partners;
  return Array.isArray(list) ? list.filter((p) => p?.folder) : [];
}

function ymdFromParts(y: string, m: string, d: string): string {
  return `${y}-${m}-${d}`;
}

function inRange(ymd: string, from: string, to: string): boolean {
  return ymd >= from && ymd <= to;
}

function findKeywords(text: string): string[] {
  const found: string[] = [];
  const seen = new Set<string>();
  const re = new RegExp(KEYWORD_RE.source, "gi");
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    const k = m[0];
    const key = k.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      found.push(k);
    }
  }
  return found;
}

function isKamiooyaText(text: string): boolean {
  if (!KEYWORD_RE.test(text)) return false;
  if (EXCLUDE_RE.test(text) && !/神大家|物件|融資|空室|LEAF|ミニテック|買付|決済/i.test(text)) {
    return false;
  }
  return true;
}

function parseBlocks(md: string): Array<{
  date: string;
  partner: string;
  direction: string;
  titleTail: string;
  body: string;
}> {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const blocks: Array<{
    date: string;
    partner: string;
    direction: string;
    titleTail: string;
    body: string;
  }> = [];
  let cur: (typeof blocks)[0] | null = null;
  for (const line of lines) {
    const m = line.match(HEADING_RE);
    if (m) {
      if (cur) blocks.push(cur);
      cur = {
        date: ymdFromParts(m[1], m[2], m[3]),
        partner: m[4].trim(),
        direction: m[5].trim(),
        titleTail: m[6].trim(),
        body: "",
      };
      continue;
    }
    if (cur) {
      cur.body += (cur.body ? "\n" : "") + line;
    }
  }
  if (cur) blocks.push(cur);
  return blocks;
}

function subjectOf(block: {
  titleTail: string;
  body: string;
}): string {
  const sm = block.body.match(SUBJECT_RE);
  if (sm?.[1]) return sm[1].replace(/\s+/g, " ").trim().slice(0, 120);
  const t = block.titleTail.replace(/\s+/g, " ").trim();
  return t.slice(0, 120) || "（件名なし）";
}

export async function digestYoritooriRange(
  from: string,
  to: string,
  opts?: { maxLines?: number },
): Promise<YoritooriDigestResult> {
  const maxLines = opts?.maxLines ?? 40;
  const notices: string[] = [];
  const skipped: string[] = [];
  const lines: YoritooriDigestLine[] = [];

  if (!graphConfigured()) {
    return {
      ok: false,
      from,
      to,
      lines: [],
      notices: [
        "OneDrive未配線（MS_GRAPH_*）。やり取り集約はスキップ",
      ],
      skipped: loadPartners().map((p) => p.folder),
    };
  }

  const partners = loadPartners();
  if (!partners.length) {
    return {
      ok: true,
      from,
      to,
      lines: [],
      notices: ["glucon_sources.json の yoritoori_partners が空"],
      skipped: [],
    };
  }

  for (const p of partners) {
    const rel = partnerYoritooriRelPath(p.folder);
    try {
      const text = await readOnedriveText(rel);
      if (!text.trim()) {
        skipped.push(`${p.folder}:empty`);
        continue;
      }
      const blocks = parseBlocks(text);
      for (const b of blocks) {
        if (!inRange(b.date, from, to)) continue;
        const hay = `${b.titleTail}\n${b.body}`;
        if (!isKamiooyaText(hay)) continue;
        lines.push({
          date: b.date,
          partner: p.name || b.partner || p.folder,
          folder: p.folder,
          direction: b.direction,
          subject: subjectOf(b),
          keywords: findKeywords(hay).slice(0, 6),
        });
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      skipped.push(p.folder);
      notices.push(`${p.folder}: ${msg}`.slice(0, 140));
    }
  }

  lines.sort((a, b) =>
    a.date === b.date
      ? a.partner.localeCompare(b.partner, "ja")
      : a.date.localeCompare(b.date),
  );

  const clipped = lines.slice(0, maxLines);
  if (lines.length > maxLines) {
    notices.push(
      `やり取り ${lines.length} 件中 ${maxLines} 件まで表示（古い順）`,
    );
  }

  return {
    ok: true,
    from,
    to,
    lines: clipped,
    notices,
    skipped,
  };
}

export function formatYoritooriDigestText(
  result: YoritooriDigestResult,
): string {
  if (!result.lines.length) {
    const skip = result.skipped.length
      ? `（スキップ: ${result.skipped.join(", ")}）`
      : "";
    return `（期間内の不動産関連やり取りなし）${skip}`;
  }
  return result.lines
    .map(
      (l) =>
        `- ${l.date} [${l.partner}] ${l.direction}: ${l.subject}` +
        (l.keywords.length ? `（${l.keywords.join(", ")}）` : ""),
    )
    .join("\n");
}
