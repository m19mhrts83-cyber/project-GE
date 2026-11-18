/**
 * メールの振り返り（/mail）の集計。判断ログ（owner_decisions）とメール（triage_items）を数えるだけ。
 * DB にもネットにも触らない（読み込みは app/mail/page.tsx）。AI も使わない。
 * 処置そのものは判断デスク（loopware /desk）で行い、ここでは振り返りだけを見せる。
 */

export const DAY_MS = 86400_000;
const JST_MS = 9 * 3600_000;

export type Decision = {
  id: number | string;
  decided_at: string;
  surface: string;
  action: string;
  partner?: string | null;
  lane?: string | null;
  final_text?: string | null;
  edited?: boolean | null;
  payload?: Record<string, unknown> | null;
};

export type MailRow = { created_at: string; lane: string | null };

function pl(r: { payload?: Record<string, unknown> | null }): Record<string, unknown> {
  return r.payload && typeof r.payload === "object" ? r.payload : {};
}

function jst(iso: string): Date {
  return new Date(Date.parse(iso) + JST_MS);
}

/** JST の「M/D」 */
export function md(iso: string): string {
  const d = jst(iso);
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
}

/** JST の日付キー YYYY-MM-DD */
export function dayKey(iso: string): string {
  return jst(iso).toISOString().slice(0, 10);
}

/** JST の週の月曜（YYYY-MM-DD） */
export function weekKey(iso: string): string {
  const d = jst(iso);
  const dow = (d.getUTCDay() + 6) % 7; // 月=0
  return new Date(d.getTime() - dow * DAY_MS).toISOString().slice(0, 10);
}

/** 判断デスク・Slack の action を5つの色に寄せる（それ以外は数えない） */
export const KIND_OF_ACTION: Record<string, Kind> = {
  sent: "sent",
  todoist: "todo",
  hesitated: "hesitate",
  unseen: "unseen",
  skipped: "skip",
};
export type Kind = "sent" | "todo" | "hesitate" | "unseen" | "skip";
export const KINDS: Kind[] = ["sent", "todo", "hesitate", "unseen", "skip"];
export const KIND_LABEL: Record<Kind, string> = {
  sent: "送った",
  todo: "ToDoへ",
  hesitate: "迷った",
  unseen: "未判断のまま",
  skip: "見送り",
};

export type DayBar = { key: string; label: string } & Record<Kind, number>;

/** 直近 days 日（今日を含む）の日別内訳 */
export function dailyBreakdown(rows: Decision[], days: number, now: Date = new Date()): DayBar[] {
  const out: DayBar[] = [];
  const idx = new Map<string, DayBar>();
  for (let i = days - 1; i >= 0; i--) {
    const iso = new Date(now.getTime() - i * DAY_MS).toISOString();
    const bar: DayBar = { key: dayKey(iso), label: md(iso), sent: 0, todo: 0, hesitate: 0, unseen: 0, skip: 0 };
    out.push(bar);
    idx.set(bar.key, bar);
  }
  for (const r of rows) {
    if (r.surface !== "triage") continue;
    const k = KIND_OF_ACTION[r.action];
    const bar = k ? idx.get(dayKey(r.decided_at)) : undefined;
    if (bar && k) bar[k] += 1;
  }
  return out;
}

/** 同じ1分に10件以上まとめて押した判断（一括見送りなど）。時間帯の傾向から外す */
export function bulkMinutes(rows: Decision[], threshold = 10): Set<string> {
  const c = new Map<string, number>();
  for (const r of rows) {
    if (r.surface !== "triage") continue;
    const m = r.decided_at.slice(0, 16);
    c.set(m, (c.get(m) || 0) + 1);
  }
  return new Set([...c.entries()].filter(([, n]) => n >= threshold).map(([m]) => m));
}

export function bulkCount(rows: Decision[], bulk: Set<string>): number {
  return rows.filter((r) => r.surface === "triage" && bulk.has(r.decided_at.slice(0, 16))).length;
}

/** JST の時間帯別（0〜23時）。一括押しは除く */
export function hourly(rows: Decision[], bulk: Set<string>): number[] {
  const h = new Array(24).fill(0) as number[];
  for (const r of rows) {
    if (r.surface !== "triage" || !KIND_OF_ACTION[r.action]) continue;
    if (bulk.has(r.decided_at.slice(0, 16))) continue;
    h[jst(r.decided_at).getUTCHours()] += 1;
  }
  return h;
}

/** 件数の多い時間帯（上位 n、0件は除く） */
export function peakHours(h: number[], n = 3): number[] {
  return h
    .map((v, i) => ({ v, i }))
    .filter((x) => x.v > 0)
    .sort((a, b) => b.v - a.v || a.i - b.i)
    .slice(0, n)
    .map((x) => x.i)
    .sort((a, b) => a - b);
}

export type WeekVol = { key: string; label: string; partner: number; general: number };

/** 週ごとに届いたメール（パートナー／その他）。今週（途中）は含めない */
export function weeklyVolume(rows: MailRow[], weeks: number, now: Date = new Date()): WeekVol[] {
  const thisWeek = weekKey(now.toISOString());
  const out: WeekVol[] = [];
  const idx = new Map<string, WeekVol>();
  for (let i = weeks; i >= 1; i--) {
    const iso = new Date(Date.parse(thisWeek + "T00:00:00Z") - i * 7 * DAY_MS - JST_MS).toISOString();
    const key = weekKey(iso);
    const w: WeekVol = { key, label: md(key + "T00:00:00+09:00"), partner: 0, general: 0 };
    out.push(w);
    idx.set(key, w);
  }
  for (const r of rows) {
    const w = idx.get(weekKey(r.created_at));
    if (!w) continue;
    if (r.lane === "partner") w.partner += 1;
    else if (r.lane === "general") w.general += 1;
  }
  return out;
}

export function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

export type Kpis = {
  decided: number;
  bulk: number;
  sent: number;
  sentPerDay: number;
  sentUnedited: number;
  sentTotalForEdit: number;
  missOk: number;
  missTotal: number;
  skipped: number;
  skippedWithReason: number;
  decideMsMedian: number | null;
};

function hasReason(r: Decision): boolean {
  const p = pl(r);
  const tags = p.reason_tags;
  if (Array.isArray(tags) && tags.length) return true;
  return typeof p.reason === "string" && p.reason.trim() !== "";
}

export function kpis(rows: Decision[], days: number, bulk: Set<string>): Kpis {
  const triage = rows.filter((r) => r.surface === "triage" && KIND_OF_ACTION[r.action]);
  const sentRows = rows.filter((r) => (r.surface === "triage" || r.surface === "draft_review") && r.action === "sent");
  const triageSent = triage.filter((r) => r.action === "sent");
  const editKnown = sentRows.filter((r) => typeof r.edited === "boolean");
  const miss = rows.filter((r) => r.surface === "triage_miss" && (r.action === "good" || r.action === "wrong"));
  const skipped = triage.filter((r) => r.action === "skipped");
  const ms = triage
    .map((r) => Number(pl(r).decide_ms))
    .filter((v) => Number.isFinite(v) && v > 0 && v < 30 * 60_000);
  return {
    decided: triage.length,
    bulk: bulkCount(triage, bulk),
    sent: triageSent.length,
    sentPerDay: days > 0 ? triageSent.length / days : 0,
    sentUnedited: editKnown.filter((r) => r.edited === false).length,
    sentTotalForEdit: editKnown.length,
    missOk: miss.filter((r) => r.action === "good").length,
    missTotal: miss.length,
    skipped: skipped.length,
    skippedWithReason: skipped.filter(hasReason).length,
    decideMsMedian: median(ms),
  };
}

/* ---------- 私のスタイル（送った本文から数えるだけ・AIなし） ---------- */

export type StyleStats = {
  n: number;
  avgLen: number | null;
  shortest: number | null;
  longest: number | null;
  closings: { text: string; n: number }[];
  openings: { text: string; n: number }[];
};

function lines(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((l) => l.replace(/\s+/g, " ").trim())
    .filter(Boolean);
}

const SIGN_RE = /^(松野|松野\s*真治|まつの|Matsuno.*|--+|―+)$/i;
const ADDRESS_RE = /(様|さま|さん|殿|御中|各位)[、。]?$/;

/** 署名を除いた最後の1行（結びのあいさつ） */
export function closingLine(text: string): string | null {
  const ls = lines(text);
  while (ls.length && (SIGN_RE.test(ls[ls.length - 1]) || ls[ls.length - 1].length <= 4)) ls.pop();
  const last = ls[ls.length - 1];
  return last && last.length <= 40 ? last : null;
}

/** 宛名の次の1行（書き出し）。最初の「。」まで */
export function openingLine(text: string): string | null {
  const ls = lines(text);
  if (ls.length && ADDRESS_RE.test(ls[0]) && ls[0].length <= 30) ls.shift();
  const first = ls[0];
  if (!first) return null;
  const cut = first.split("。")[0];
  return cut && cut.length <= 40 ? cut + (first.includes("。") ? "。" : "") : null;
}

function top(xs: (string | null)[], n: number): { text: string; n: number }[] {
  const c = new Map<string, number>();
  for (const x of xs) if (x) c.set(x, (c.get(x) || 0) + 1);
  return [...c.entries()]
    .map(([text, k]) => ({ text, n: k }))
    .sort((a, b) => b.n - a.n || a.text.length - b.text.length)
    .slice(0, n);
}

export function styleStats(rows: Decision[]): StyleStats {
  const texts = rows
    .filter((r) => r.action === "sent" && typeof r.final_text === "string" && r.final_text.trim())
    .map((r) => String(r.final_text));
  const lens = texts.map((t) => t.replace(/\s+/g, "").length);
  return {
    n: texts.length,
    avgLen: lens.length ? Math.round(lens.reduce((a, b) => a + b, 0) / lens.length) : null,
    shortest: lens.length ? Math.min(...lens) : null,
    longest: lens.length ? Math.max(...lens) : null,
    closings: top(texts.map(closingLine), 3),
    openings: top(texts.map(openingLine), 3),
  };
}

/* ---------- 気づき（決まった型の文。AIなし） ---------- */

export type Insight = { title: string; body: string; hint: string; tone: "alert" | "info" | "good" };

export function insights(input: {
  k: Kpis;
  weeks: WeekVol[];
  peaks: number[];
  totals: { partner: number; general: number; since: string | null };
}): Insight[] {
  const { k, weeks, peaks, totals } = input;
  const out: Insight[] = [];

  if (k.skipped >= 10) {
    const r = k.skippedWithReason / k.skipped;
    if (r < 0.2) {
      out.push({
        tone: "alert",
        title: "見送りの理由が残っていない",
        body: `見送り ${k.skipped} 件のうち、理由が付いたものは ${k.skippedWithReason} 件。理由がないと「なぜ下げたか」を次に活かせません。`,
        hint: "判断デスクで見送るときに理由を一つ選ぶ",
      });
    }
  }

  const all = totals.partner + totals.general;
  if (all >= 50) {
    const share = Math.round((totals.partner / all) * 100);
    out.push({
      tone: "info",
      title: `パートナーのメールは全体の約${share}%`,
      body: `${totals.since ? `${totals.since}以降、` : ""}その他メール ${totals.general.toLocaleString("ja-JP")} 件に対し、パートナーは ${totals.partner.toLocaleString("ja-JP")} 件。大事なメールは少数で、埋もれやすい。`,
      hint: "パートナーは判断デスクで先に出す",
    });
  }

  const pv = weeks.map((w) => w.partner);
  const med = median(pv.filter((v) => v > 0));
  if (med && weeks.length >= 4) {
    let best = weeks[0];
    for (const w of weeks) if (w.partner > best.partner) best = w;
    const ratio = best.partner / med;
    if (ratio >= 2) {
      out.push({
        tone: "info",
        title: `${best.label}の週にパートナーが急増`,
        body: `この週は ${best.partner} 件（ふだんの週の約${Math.round(ratio * 10) / 10}倍）。何があった週かを残しておくと、後から振り返れます。`,
        hint: "急増した週に一言メモを残す",
      });
    }
  }

  if (k.missTotal >= 10) {
    const r = k.missOk / k.missTotal;
    out.push({
      tone: r >= 0.9 ? "good" : "alert",
      title: r >= 0.9 ? "仕分けはほぼ合っている" : "仕分けの見落としが目立つ",
      body: `見落とし確認 ${k.missTotal} 件中 ${k.missOk} 件が「合っていた」。`,
      hint: r >= 0.9 ? "見落とし確認の件数を減らしてよい" : "外れた形を週次でルール案にする",
    });
  }

  if (peaks.length) {
    out.push({
      tone: "info",
      title: `判断は ${peaks.map((h) => `${h}時`).join("・")}台に集中`,
      body: "この時間に判断デスクが空いているように、拾い上げの時刻をそろえると待ちが減ります。",
      hint: "拾い上げの定時と見比べる",
    });
  }

  return out.slice(0, 3);
}
