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
  payload?: Record<string, unknown> | null;
};

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
  return ID_RE.test(id || "") && !/^re-vendor-/i.test(id);
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

/** デスクに出す行か（業者返信・オープンチャットは別の係） */
export function isDeskRow(r: TriageRow): boolean {
  if (!isDeskItemId(r.id)) return false;
  if (String(r.status || "pending") !== "pending") return false;
  const lane = String(r.lane || "");
  if (lane === "openchat") return false;
  const pl = obj(r.payload);
  if (pl.re_vendor_reply) return false;
  return true;
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
