/**
 * コミュニケーション台帳（comm_items）から「この相手との直近のやり取り」を作る純粋関数。
 * 読み出し（Supabase）は lib/commHistoryServer.ts。ここは DB に触らない（テスト用）。
 *
 * 名簿 comm_parties には同じ相手が 2 行ある（例: partner:102_ミニテック と partner:P102_ミニテック）。
 * 画面と下書きでは「名前」でまとめて 1 社として扱う。
 */

export type CommParty = {
  party_id: string;
  name: string;
  partner_folder: string | null;
  emails?: string[] | null;
  email_domains?: string[] | null;
};

export type CommItem = {
  id: string;
  party_id: string | null;
  channel: string;
  direction: "inbound" | "outbound" | string;
  occurred_at: string;
  subject?: string | null;
  summary?: string | null;
  body_text?: string | null;
};

export const CHANNEL_LABEL: Record<string, string> = {
  gmail: "メール",
  chatwork: "Chatwork",
  line: "LINE",
  line_oa: "LINE公式",
  imessage: "iMessage",
  slack: "Slack",
  obsidian: "メモ",
  other: "その他",
};

/** "P806_神大家AI推進" と "806_神大家AI推進" を同じにする */
export function normFolder(folder: string | null | undefined): string {
  return String(folder || "")
    .trim()
    .replace(/^P(?=\d)/, "");
}

/** 返信対象（triage の folder / partner / 差出人）から、同じ相手の party_id をすべて返す */
export function matchPartyIds(
  parties: CommParty[],
  q: { folder?: string | null; partner?: string | null; email?: string | null },
): string[] {
  const folder = normFolder(q.folder);
  const partner = String(q.partner || "").trim();
  const email = String(q.email || "").trim().toLowerCase();
  const domain = email.includes("@") ? email.split("@").pop() || "" : "";

  let hit = parties.find((p) => folder && normFolder(p.partner_folder) === folder);
  if (!hit && email) hit = parties.find((p) => (p.emails || []).some((e) => e.toLowerCase() === email));
  if (!hit && partner) hit = parties.find((p) => p.name === partner);
  if (!hit && domain) hit = parties.find((p) => (p.email_domains || []).some((d) => d.toLowerCase() === domain));
  if (!hit) return [];
  return parties.filter((p) => p.name === hit!.name).map((p) => p.party_id);
}

/** 台帳の本文から md の折りたたみ・Chatwork の引用を外して読める形にする */
export function cleanBody(text: string | null | undefined): string {
  return String(text || "")
    .replace(/<summary>[\s\S]*?<\/summary>/gi, "")
    .replace(/<\/?details>/gi, "")
    .replace(/\[qt\][\s\S]*?\[\/qt\]/gi, "")
    .replace(/\[(?:qtmeta|To|rp|piconname|picon)[^\]]*\]/gi, "")
    .replace(/\[\/?(?:info|title|code|hr)\]/gi, "")
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function clip(text: string, max: number): string {
  const t = text.trim();
  return t.length <= max ? t : `${t.slice(0, max)}…`;
}

/** JST の "2026/11/18 19:22" */
export function jstStamp(iso: string): string {
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "";
  const d = new Date(t + 9 * 3600_000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getUTCFullYear()}/${p(d.getUTCMonth() + 1)}/${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
}

export function itemText(it: CommItem): string {
  const body = cleanBody(it.body_text);
  if (body) return body;
  return cleanBody(it.summary || it.subject || "");
}

function line(it: CommItem, max: number): string {
  const who = it.direction === "outbound" ? "自分→相手" : "相手→自分";
  const ch = CHANNEL_LABEL[it.channel] || it.channel;
  const subj = it.channel === "gmail" && it.subject ? `件名「${clip(cleanBody(it.subject), 60)}」 ` : "";
  return `【${jstStamp(it.occurred_at)}｜${ch}｜${who}】${subj}\n${clip(itemText(it), max)}`;
}

/**
 * 下書き AI に渡す「最近のやり取り」。古い→新しいの順。
 * recent: 相手を問わず直近（新しい順で受け取る）／mine: 自分が送った文面（新しい順）。
 * recent に含まれる自分の文面は mine から外す（同じものを二度見せない）。
 */
export function formatHistoryBlock(
  who: string,
  recent: CommItem[],
  mine: CommItem[],
  opts: { maxChars?: number; perItem?: number; minePerItem?: number } = {},
): string {
  const maxChars = opts.maxChars ?? 6000;
  const perItem = opts.perItem ?? 400;
  const minePerItem = opts.minePerItem ?? 300;
  if (recent.length === 0 && mine.length === 0) return "";

  const head = `## ${who} との最近のやり取り（台帳・チャネル横断・古い順）`;
  const recentLines = [...recent].reverse().map((it) => line(it, perItem));

  const seen = new Set(recent.map((r) => r.id));
  const extra = mine.filter((m) => !seen.has(m.id) && m.direction === "outbound");
  const mineLines = extra.length
    ? [
        `## 松野さんがこれまでに ${who} へ送った文面（言い回しの参考）`,
        ...extra.map(
          (it) => `【${jstStamp(it.occurred_at)}｜${CHANNEL_LABEL[it.channel] || it.channel}】\n${clip(itemText(it), minePerItem)}`,
        ),
      ]
    : [];

  const build = () => [...(recentLines.length ? [head, ...recentLines] : []), ...mineLines].join("\n\n");
  let out = build();
  // 長すぎるときは古いやり取りから落とす（直近3件と自分の文面は残す）
  while (out.length > maxChars && recentLines.length > 3) {
    recentLines.shift();
    out = build();
  }
  return out.length > maxChars ? out.slice(-maxChars) : out;
}

export type PartySummary = {
  name: string;
  partyIds: string[];
  folder: string;
  total: number;
  last30: number;
  latestAt: string;
  latest: CommItem[];
};

/** 直近の台帳行（新しい順）を相手ごとにまとめ、最後にやり取りした順に並べる */
export function summarizeByParty(
  parties: CommParty[],
  items: CommItem[],
  now: Date = new Date(),
  perParty = 3,
): PartySummary[] {
  const nameOf = new Map(parties.map((p) => [p.party_id, p.name]));
  const byName = new Map<string, PartySummary>();
  for (const p of parties) {
    const s = byName.get(p.name);
    const folder = p.partner_folder || "";
    if (s) {
      s.partyIds.push(p.party_id);
      if (/^P\d/.test(folder)) s.folder = folder;
    } else {
      byName.set(p.name, { name: p.name, partyIds: [p.party_id], folder, total: 0, last30: 0, latestAt: "", latest: [] });
    }
  }
  const cutoff = now.getTime() - 30 * 86400_000;
  for (const it of items) {
    const name = it.party_id ? nameOf.get(it.party_id) : undefined;
    if (!name) continue;
    const s = byName.get(name)!;
    s.total += 1;
    if (Date.parse(it.occurred_at) >= cutoff) s.last30 += 1;
    if (!s.latestAt || it.occurred_at > s.latestAt) s.latestAt = it.occurred_at;
    if (s.latest.length < perParty) s.latest.push(it);
  }
  return [...byName.values()]
    .filter((s) => s.total > 0)
    .sort((a, b) => (a.latestAt < b.latestAt ? 1 : a.latestAt > b.latestAt ? -1 : 0));
}
