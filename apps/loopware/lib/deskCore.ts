/**
 * 判断デスク（/desk）の外部に依存しない部品。
 * - triage_items の行 → 1枚のカード
 * - 並び順（Slack に出した順の点数 → 新しい順）
 * - ボタン → 判断ログの action
 */

export type TriageRow = {
  id: string;
  status?: string | null;
  subject?: string | null;
  partner?: string | null;
  from_email?: string | null;
  lane?: string | null;
  kind?: string | null;
  summary?: string | null;
  draft_text?: string | null;
  original_body?: string | null;
  received_at?: string | null;
  priority?: string | null;
  gmail_thread_id?: string | null;
  payload?: Record<string, unknown> | null;
};

/** スレッドの1つ前までのやりとり（仕分けが payload.thread_context に入れる）。mine=松野さんが送ったもの */
export type ThreadMsg = { at: string; mine: boolean; subject: string; body: string };

export type DeskCard = {
  id: string;
  subject: string;
  who: string;
  fromEmail: string;
  lane: string;
  kind: string;
  summary: string;
  bodyLines: string[];
  draftLines: string[];
  receivedAt: string | null;
  priority: string;
  threadId: string;
  /** 1つ前までのやりとり（古い順）。自分が送ったメールもここに入る */
  thread: ThreadMsg[];
  /** すでに返信・見送りした履歴の説明（同じスレッド／同じ相手） */
  history: string[];
  score: number | null;
  appliedRules: string[];
  postedToSlack: boolean;
  hesitatedAt: string | null;
  /** 迷ったときに選ばれた「残っている理由」 */
  stayReason: string | null;
};

/** デスクのボタン。返信は Jarvis の返信画面で送る（ここでは送らない） */
export const DESK_CHOICES = ["skip", "todo", "done", "hesitate"] as const;
export type DeskChoice = (typeof DESK_CHOICES)[number];

/** ボタン → 判断ログの action（triage トリガーの status と同じ語） */
export const CHOICE_ACTION: Record<DeskChoice, string> = {
  skip: "skipped",
  todo: "todoist",
  done: "done",
  hesitate: "hesitated",
};

/** ボタン → Jarvis の短いリンク（/api/g/ma/{action}/{id}）の action。迷うは状態を変えない */
export const CHOICE_MA: Partial<Record<DeskChoice, "skip" | "todoist" | "done">> = {
  skip: "skip",
  todo: "todoist",
  done: "done",
};

const ID_RE = /^[a-zA-Z0-9_.:-]{6,80}$/;

export function isDeskItemId(id: string): boolean {
  return ID_RE.test(id || "") && !isVendorItemId(id);
}

/** 業者返信（516）の案件。判断デスクには出さないが、見落とし（/misses）には出る */
export function isVendorItemId(id: string): boolean {
  return /^re-vendor-/i.test(id || "");
}

/** triage_items の id として正しい形か（業者返信も含む。見落としの判断用） */
export function isTriageItemId(id: string): boolean {
  return ID_RE.test(id || "");
}

function obj(x: unknown): Record<string, unknown> {
  return x && typeof x === "object" && !Array.isArray(x) ? (x as Record<string, unknown>) : {};
}

function lines(text: string | null | undefined, max: number): string[] {
  return String(text || "")
    .replace(/\r/g, "")
    .split("\n")
    .map((l) => l.trimEnd())
    .filter((l, i, a) => l || (i > 0 && a[i - 1]))
    .slice(0, max);
}

/** 本文から引用・署名を落として先頭だけ */
function bodyHead(text: string | null | undefined): string[] {
  const out: string[] = [];
  for (const l of lines(text, 60)) {
    if (/^>/.test(l) || /^-{2,}\s*$/.test(l) || /^(On .+wrote:|.+のメッセージ:)$/.test(l)) break;
    out.push(l);
    if (out.length >= 12) break;
  }
  return out;
}

function threadOf(x: unknown): ThreadMsg[] {
  if (!Array.isArray(x)) return [];
  const out: ThreadMsg[] = [];
  for (const e of x.slice(-4)) {
    const o = obj(e);
    const body = String(o.body || "").slice(0, 900);
    if (!body.trim()) continue;
    out.push({ at: String(o.at || "").slice(0, 20), mine: Boolean(o.mine), subject: String(o.subject || "").slice(0, 120), body });
  }
  return out;
}

export function toCard(r: TriageRow): DeskCard {
  const pl = obj(r.payload);
  const digest = obj(pl.slack_ma_digest);
  const score = typeof digest.score === "number" ? digest.score : null;
  const rules = Array.isArray(pl.applied_rules) ? pl.applied_rules.map(String) : [];
  const draftRules = Array.isArray(pl.draft_rules) ? pl.draft_rules.map(String) : [];
  return {
    id: r.id,
    subject: String(r.subject || "（件名なし）").slice(0, 200),
    who: String(r.partner || r.from_email || "").slice(0, 120),
    fromEmail: String(r.from_email || ""),
    lane: String(r.lane || ""),
    kind: String(r.kind || "mail"),
    summary: String(digest.summary || r.summary || "").slice(0, 400),
    bodyLines: bodyHead(r.original_body),
    draftLines: lines(r.draft_text, 40),
    receivedAt: r.received_at || null,
    priority: String(r.priority || ""),
    threadId: String(r.gmail_thread_id || ""),
    thread: threadOf(pl.thread_context),
    history: [],
    score,
    appliedRules: Array.from(new Set([...rules, ...draftRules])),
    postedToSlack: Boolean(pl.slack_ma_posted_at),
    hesitatedAt: typeof pl.loopware_hesitated_at === "string" ? pl.loopware_hesitated_at : null,
    stayReason: typeof pl.loopware_stay_reason === "string" ? pl.loopware_stay_reason : null,
  };
}

/** Slack に出したもの → 点数 → 新しい順。迷ったものは後ろへ */
export function orderCards(cards: DeskCard[]): DeskCard[] {
  return [...cards].sort((a, b) => {
    if (!!a.hesitatedAt !== !!b.hesitatedAt) return a.hesitatedAt ? 1 : -1;
    if (a.postedToSlack !== b.postedToSlack) return a.postedToSlack ? -1 : 1;
    const sa = a.score ?? -9999;
    const sb = b.score ?? -9999;
    if (sa !== sb) return sb - sa;
    return String(b.receivedAt || "").localeCompare(String(a.receivedAt || ""));
  });
}

/** デスクに出す行か（業者返信・オープンチャットは別の係。自動のお知らせ・メルマガはまとめ側） */
export function isDeskRow(r: TriageRow): boolean {
  if (!isDeskItemId(r.id)) return false;
  if (String(r.status || "pending") !== "pending") return false;
  const lane = String(r.lane || "");
  if (lane === "openchat") return false;
  const pl = obj(r.payload);
  if (pl.re_vendor_reply) return false;
  return deskWorthy(r);
}

// ---- 人が判断するカードか（2026-11-10）----
// 判断デスクに未判断が 266 件並び、Slack の要対応ふるいを通ったのは 8 件だけだった。
// カードにするのは「パートナー」「Slack に出した」「迷った」「人が書いたメール」「支払いの失敗」。
// それ以外（カード・銀行の通知、認証コード、メルマガ、ざっと見る用）はダッシュボードの「その他メール」へ。
// 人が書いたかの見分けは scripts/jarvis_mail_human.py と同じ（Jarvis 側 lib/deskWorthy.ts にも同じ写し）。

/** 自動送信でも必ず見る（支払いの失敗・引き落としできなかった） */
export const PAY_FAIL_RE =
  /(未済|ご利用いただけませんでした|決済(が)?(失敗|エラー|できませんでした)|お支払い(のご確認|エラー|が確認できません)|引き?落とし(が)?(でき|され)ませんでした|振替不能|残高不足)/;

const BULK_BODY_RE =
  /(配信停止|配信解除|送信専用|返信できません|返信いただいても|ご返信いただいても|unsubscribe|メールマガジン|メルマガ|配信元|受信設定|配信を希望されない|オプトアウト|このメールアドレスは送信のみ)/i;
const REPLY_SUBJECT_RE = /^\s*(re|ｒｅ|返信)\s*[:：]/i;
const BRAND_SUBJECT_RE = /【[^】]{2,40}】/;
const ADDRESSED_RE = /松野\s*(真治)?\s*(様|さま|さん)/;
const FREE_MAIL_RE =
  /@(ezweb\.ne\.jp|docomo\.ne\.jp|softbank\.ne\.jp|i\.softbank\.jp|au\.com|gmail\.com|icloud\.com|me\.com|outlook\.(com|jp)|hotmail\.(com|co\.jp)|yahoo\.co\.jp|ymail\.ne\.jp)$/i;
const ROLE_TOKENS = new Set(
  ("info information support mail noreply no reply notice notification notifications news newsletter team service " +
    "statement post master postmaster campaign matching official customer customers center web mobile welcome invoice " +
    "statements action office account accounts desk admin sales contact direct help system staff member members " +
    "store shop order orders billing press pr marketing").split(" "),
);

function mailAddr(from: string): string {
  const s = String(from || "").trim();
  const m = s.match(/<([^>]+)>/);
  return (m ? m[1] : s).trim().toLowerCase();
}

function looksPersonalLocal(addr: string): boolean {
  const local = addr.split("@")[0].split("+")[0];
  const toks = local.split(/[._-]+/).filter(Boolean);
  if (!toks.length || toks.some((t) => ROLE_TOKENS.has(t) || ROLE_TOKENS.has(t.replace(/\d+$/, "")))) return false;
  return toks.length >= 2 && toks.every((t) => /^[a-z]+$/i.test(t));
}

/** 人が書いたメールか（scripts/jarvis_mail_human.py looks_human_mail と同じ判定） */
export function looksHumanMail(fromEmail: string, subject: string, body: string): boolean {
  const b = String(body || "");
  const subj = String(subject || "");
  if (BULK_BODY_RE.test(b)) return false;
  const addr = mailAddr(fromEmail);
  const addressed = ADDRESSED_RE.test(b.slice(0, 400));
  if (REPLY_SUBJECT_RE.test(subj)) return true;
  if (FREE_MAIL_RE.test(addr)) return true;
  const branded = BRAND_SUBJECT_RE.test(subj);
  if (addressed && !branded) return true;
  if (addressed && looksPersonalLocal(addr)) return true;
  return false;
}

/** 人が判断するカードにするか */
export function deskWorthy(r: TriageRow): boolean {
  const pl = obj(r.payload);
  if (String(r.lane || "") === "partner") return true;
  if (pl.slack_ma_posted_at || pl.loopware_hesitated_at || pl.loopware_miss) return true;
  if (PAY_FAIL_RE.test(String(r.subject || ""))) return true;
  if (String(r.kind || "mail") === "skim") return false;
  // 家族などが携帯・フリーメールから転送してきたもの（転送元の配信停止の文言で落とさない）
  if (/^\s*(fwd?|転送)\s*[:：]/i.test(String(r.subject || "")) && FREE_MAIL_RE.test(mailAddr(String(r.from_email || "")))) return true;
  return looksHumanMail(String(r.from_email || ""), String(r.subject || ""), String(r.original_body || ""));
}

/** 「3時間前」などの表示 */
export function agoLabel(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "";
  const m = Math.max(0, Math.round((now.getTime() - t) / 60000));
  if (m < 60) return `${m}分前`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h}時間前`;
  return `${Math.round(h / 24)}日前`;
}

// ---------------------------------------------------------------- 残り案件（view=left）

/** 残りに出すか: 迷ったもの、または届いてから 24 時間たって未判断のもの */
export function isLeftover(c: DeskCard, now: Date = new Date()): boolean {
  if (c.hesitatedAt) return true;
  if (!c.receivedAt) return false;
  const t = Date.parse(c.receivedAt);
  return Number.isFinite(t) && now.getTime() - t >= 24 * 3600_000;
}

export type NextEffect = "snooze3" | "todo" | "skip" | "reply";
export type NextStep = { id: string; text: string; effect: NextEffect; why: string };

function ageHours(c: DeskCard, now: Date): number {
  const t = c.receivedAt ? Date.parse(c.receivedAt) : NaN;
  return Number.isFinite(t) ? (now.getTime() - t) / 3600_000 : 0;
}

/**
 * 次の一手（型で決める。AI は使わない）。良い→そのとおりに動かす／違う→記録して理由を聞く。
 * 型の id は週次で「どの型が当たるか」を数えるのに使う。
 */
export function nextStepFor(c: DeskCard, now: Date = new Date()): NextStep {
  const h = ageHours(c, now);
  if (c.stayReason === "waiting") {
    return { id: "wait_snooze3", effect: "snooze3", text: "返事待ちなので、3日後にもう一度出します", why: "誰かの返事待ち" };
  }
  if (c.stayReason === "no_time") {
    return { id: "notime_todo", effect: "todo", text: "ToDo に入れて、時間のあるときに返します", why: "時間がない" };
  }
  if (c.stayReason === "need_info") {
    return c.draftLines.length
      ? { id: "needinfo_reply", effect: "reply", text: "返信画面を開いて、確認の一文を足して返します", why: "情報が足りない" }
      : { id: "needinfo_todo", effect: "todo", text: "調べることを ToDo に入れます", why: "情報が足りない" };
  }
  if (!c.postedToSlack && (c.score ?? 0) < 30 && h >= 72) {
    return { id: "old_low_skip", effect: "skip", text: "3日以上たっていて優先度も低いので、見送ってよいですか", why: `${Math.round(h / 24)}日前・点数が低い` };
  }
  if (c.draftLines.length && c.lane === "partner") {
    return { id: "draft_reply", effect: "reply", text: "下書きがあるので、そのまま返信画面で送ります", why: "下書きあり" };
  }
  if (h >= 24 * 7) {
    return { id: "week_skip", effect: "skip", text: "1週間以上残っています。見送ってよいですか", why: "7日以上" };
  }
  return { id: "default_todo", effect: "todo", text: "ToDo に入れて、ここからは外します", why: "迷ったまま" };
}


// ---------------------------------------------------------------- 返信済み・見送り済みの印（2026-11-13）
// 「Slack でも見た気がする山本不動産は、お礼を送ったのか見送ったのか」が分からなかった。
// カードを出すときに、同じスレッド・同じ相手の過去の判断を並べる。

export type DecidedRow = {
  id: string;
  status: string;
  from_email?: string | null;
  gmail_thread_id?: string | null;
  updated_at?: string | null;
};

export const DECIDED_STATUSES = ["sent", "skipped", "done", "todoist"] as const;
const DECIDED_LABEL: Record<string, string> = { sent: "返信", skipped: "見送り", done: "回答不要", todoist: "ToDo" };
const DECIDED_PAST: Record<string, string> = {
  sent: "返信済み",
  skipped: "見送り済み",
  done: "回答不要にした",
  todoist: "ToDo に入れた",
};

/** gha- / gha-p- / gha-cw- を外した共通の鍵（同じメールの双子） */
export function twinKey(id: string): string {
  return String(id || "").replace(/^gha-(cw-|p-)?/, "");
}

function mmdd(iso: string | null | undefined): string {
  const t = Date.parse(iso || "");
  if (!Number.isFinite(t)) return "";
  const d = new Date(t + 9 * 3600_000); // JST
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
}

/** 同じメールの双子・自分自身は数えない。同じスレッド → 同じ相手（30日）の順に文にする */
export function historyNotes(
  card: { id: string; fromEmail: string; threadId: string },
  decided: DecidedRow[],
): string[] {
  const me = twinKey(card.id);
  const rows = decided
    .filter((r) => twinKey(r.id) !== me && r.status in DECIDED_LABEL)
    .sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
  const notes: string[] = [];
  const same = card.threadId ? rows.filter((r) => r.gmail_thread_id && r.gmail_thread_id === card.threadId) : [];
  if (same.length) {
    const r = same[0];
    notes.push(`同じスレッドで ${mmdd(r.updated_at)} に${DECIDED_PAST[r.status]}`);
  }
  const from = card.fromEmail.trim().toLowerCase();
  const sender = from ? rows.filter((r) => String(r.from_email || "").trim().toLowerCase() === from) : [];
  if (sender.length) {
    const n: Record<string, number> = {};
    for (const r of sender) n[r.status] = (n[r.status] || 0) + 1;
    const parts = ["sent", "skipped", "done", "todoist"].filter((k) => n[k]).map((k) => `${DECIDED_LABEL[k]} ${n[k]}`);
    const last = sender[0];
    notes.push(`この相手の過去30日: ${parts.join("・")}（直近は ${mmdd(last.updated_at)} ${DECIDED_LABEL[last.status]}）`);
  }
  return notes;
}

/** カードの上に出す「いまの状態」の一行 */
export function stateLine(c: Pick<DeskCard, "postedToSlack" | "hesitatedAt" | "history">): string {
  const base = c.hesitatedAt
    ? "迷って残っています"
    : c.postedToSlack
      ? "Slack に出ましたが、まだ返信も見送りもしていません"
      : "まだ判断していません";
  return base;
}
