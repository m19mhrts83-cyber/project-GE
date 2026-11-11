/**
 * 判断ログ（Supabase owner_decisions）の書き込み契約 v1。
 *
 * 入口は4つ（Slack・loopware・Jarvisダッシュボード・KURASHIFT）。どこから判断しても
 * この形に揃えてから1行残す。新しい表は作らず、payload の中身を約束で揃える。
 *
 * - 迷った（hesitated）・見ていない（unseen）は NG（skipped）に混ぜない
 * - 理由はすべて任意（空でも記録する）
 * - 同じ判断を二度送っても1行だけ残る（payload.idem_key）
 *
 * 外部に依存しない純粋な部品。正本は apps/loopware/lib/decisionContract.ts。
 * apps/jarvis-dashboard/lib/decisionContract.ts・apps/trade-desk/lib/decisionContract.ts は同じ内容の写し
 * （scripts/tests/test_decision_contract_sync.py が一致を確かめる）。
 */

export const CONTRACT_VERSION = 1;

/** どの判断か */
export const SURFACES = [
  "triage", // メール要対応（返信する／見送る／ToDo）
  "triage_miss", // 拾い漏れ（出てこなかったが本当は要対応だった）
  "triage_rule", // 送り手ルールの確認（Slack メール側）
  "mail_send", // 送信直前・直後（誤字直し・言い回し・送った後の👍/いまいち）
  "todoist_312",
  "todoist_313",
  "s9",
  "kurashift_deal", // 物件の見送り・検討（確認・進行中・内見・買付も。DB トリガーが kurashift_re_deal_events から写す）
  "kurashift_money", // 資金移動の承認・相談・取消・完了（DB トリガーが kurashift_money_ops の status 変化から写す）
  "kurashift_consult", // 相談メモ
  "kurashift_mail", // KURASHIFT 発のメール
  "zaim_category", // Zaim 費目の仕分け確認
  "rule_review", // ルール候補の採用・取り消し
  "draft_review", // チャットで作った下書きの版直し（松野さんの直し・ひとこと。scripts/jarvis_draft_decision_log.py）
  "weekly_pick", // 日曜夜の「今週の9件」（選んだ／見送った／残った理由／確定。scripts/jarvis_todoist_weekly_pick.py が反映）
  "slide_plan", // 資料：作る前の選択（構成案・観点）
  "slide_fix", // 資料：作った後の直し（直す前と後）
  "slide_rule", // 資料：次回反映案の採否
] as const;
export type Surface = (typeof SURFACES)[number];

/** どの入口から */
export const SOURCES = ["slack", "loopware", "dashboard", "kurashift", "script"] as const;
export type Source = (typeof SOURCES)[number];

/**
 * 従来の細かい入口名（slack_button / slack_link / dashboard_or_script …）を4つ＋script に寄せる。
 * 元の名前は payload.source_detail に残す。
 */
export function coarseSource(raw: string | null | undefined): Source | null {
  const s = String(raw || "").trim().toLowerCase();
  if (!s) return null;
  if ((SOURCES as readonly string[]).includes(s)) return s as Source;
  if (s.startsWith("slack")) return "slack";
  if (s.startsWith("loopware") || s === "app") return "loopware";
  if (s.startsWith("dashboard")) return "dashboard";
  if (s.startsWith("kurashift") || s.startsWith("trade")) return "kurashift";
  if (s.startsWith("script") || s.startsWith("launchd") || s.startsWith("gha") || s.startsWith("cron")) return "script";
  return null;
}

/**
 * 判断の種類。surface ごとの細かい語（create / close / adopt …）は従来どおり通すが、
 * 新しく足す語はここに並べる。
 */
export const ACTIONS = [
  // 採った
  "sent",
  "replied",
  "todo",
  "todoist",
  "adopt",
  "accept",
  "good",
  // 見送った（NG）
  "skipped",
  "reject",
  "wrong",
  // 迷った・見ていない（NG に混ぜない）
  "hesitated",
  "unseen",
  // 後で
  "snoozed",
  // 品質・ひとこと
  "meh", // いまいち
  "none_fit", // どれも違う
  "comment", // 声や文字のひとこと
  "revise", // 下書きを直した（送る前の版直し。draft_review）
  // ルール
  "rule_accept",
  "rule_once",
  "rule_reject",
  "rule_revert",
  // 次の一手（残り案件）
  "next_good",
  "next_wrong",
  // 既存（312/313/S9/triage トリガー）
  "done",
  "create",
  "dismiss",
  "close",
  "drop",
  "merge",
  "reschedule",
  "skip",
  // 今週の9件（weekly_pick）
  "pick", // 今週やる（曜日に置いた）
  "defer", // おすすめに出たが今週は見送り（候補に残す）
  "left", // 先週残ったものの振り返り（理由と次の手）
  "commit", // その週の割付を確定（反映の単位）
] as const;
export type Action = (typeof ACTIONS)[number];

/** 「採った／見送った／迷った／未判断」の4つに分ける（集計と粒の色に使う） */
export type Outcome = "take" | "ng" | "hesitate" | "none" | "later" | "note";

const OUTCOME_OF: Record<string, Outcome> = {
  sent: "take",
  replied: "take",
  todo: "take",
  todoist: "take",
  adopt: "take",
  accept: "take",
  good: "take",
  rule_accept: "take",
  next_good: "take",
  pick: "take",
  create: "take",
  done: "take",
  close: "take",
  drop: "take",
  merge: "take",
  skipped: "ng",
  reject: "ng",
  wrong: "ng",
  rule_reject: "ng",
  next_wrong: "ng",
  dismiss: "ng",
  skip: "ng",
  hesitated: "hesitate",
  unseen: "none",
  snoozed: "later",
  reschedule: "later",
  rule_once: "later",
  defer: "later",
  meh: "note",
  none_fit: "note",
  comment: "note",
  revise: "note",
  rule_revert: "note",
  left: "note",
  commit: "note",
};

export function outcomeOf(action: string): Outcome {
  return OUTCOME_OF[action] || "note";
}

/** 見送り理由（メール）。Slack 側の既存キー promo/handled/notnow もそのまま受ける */
export const MAIL_REASON_TAGS = {
  no_reply: "回答不要",
  self_or_grok: "自分発信・Grok部長",
  handled: "他で対応済み",
  notnow: "今は不要",
  not_important: "そもそも重要でない",
  promo: "宣伝・通知",
  other: "その他",
} as const;

/** 見送り理由（物件） */
export const DEAL_REASON_TAGS = {
  area: "エリア外",
  yield: "利回り不足",
  price: "価格",
  age_structure: "築年・構造",
  loan: "融資が付きにくい",
  other: "その他",
} as const;

/** 物件を進めた決め手（内見・買付へ） */
export const DEAL_TAKE_REASON_TAGS = {
  cf_ok: "CFが合う",
  area_ok: "エリアが良い",
  price_ok: "価格に納得",
  loan_ok: "融資が通りそう",
  fix_ok: "修繕が読める",
  want_see: "現地で確かめたい",
} as const;

/** 資金移動（KURASHIFT のお金の判断）：承認・相談・取消の理由 */
export const MONEY_REASON_TAGS = {
  plan_fit: "計画どおり",
  buffer: "防衛資金・バッファを守る",
  due_date: "引落・期日に間に合わせる",
  rate: "金利・手数料",
  amount_check: "金額を見直したい",
  timing: "時期をずらしたい",
  ask_someone: "誰かに相談したい",
  other: "その他",
} as const;

/** 残っている理由（迷った・見ていない案件） */
export const STAY_REASON_TAGS = {
  no_time: "時間がない",
  unsure: "迷った",
  need_info: "情報が足りない",
  waiting: "誰かの返事待ち",
} as const;

/** 今週の9件：選んだ理由 */
export const PICK_REASON_TAGS = {
  deadline: "締切が近い",
  waiting_other: "相手を待たせている",
  partner_money: "パートナー・お金の仕事",
  carried: "先週から残っている",
  small: "小さくすぐ終わる",
  interest: "興味・勢いがある",
  inlet: "入口で待っている",
  planned: "前の週の見通しで置いていた",
} as const;

/** 今週の9件：残った理由 */
export const LEFT_REASON_TAGS = {
  no_time: "時間が足りなかった",
  waiting: "相手待ち・材料待ち",
  too_big: "大きすぎた・気が重い",
  lower_priority: "優先が下がった",
  ai_dev: "AI開発に時間を使った",
} as const;

/** 資料：選ばなかった案の理由 */
export const SLIDE_PLAN_REASON_TAGS = {
  off_theme: "今回の主題とずれる",
  too_heavy: "重い",
  same_as_last: "前回と同じ",
  not_for_members: "メンバー向きでない",
  no_time: "時間が足りない",
} as const;

/** 資料：次回反映案を「今回だけ／違う」にした理由 */
export const SLIDE_RULE_REASON_TAGS = {
  by_chance: "たまたま",
  depends: "相手・回による",
  already_rule: "もう決めている",
  wording: "言い方が違う",
} as const;

/** 送った後の手応え */
export const QUALITY = ["good", "meh", "none_fit"] as const;

/** ルールの効き目の範囲 */
export const SCOPES = ["once", "partner", "always"] as const;

const KNOWN_TAGS = new Set<string>([
  ...Object.keys(MAIL_REASON_TAGS),
  ...Object.keys(DEAL_REASON_TAGS),
  ...Object.keys(DEAL_TAKE_REASON_TAGS),
  ...Object.keys(MONEY_REASON_TAGS),
  ...Object.keys(STAY_REASON_TAGS),
  ...Object.keys(PICK_REASON_TAGS),
  ...Object.keys(LEFT_REASON_TAGS),
  ...Object.keys(SLIDE_PLAN_REASON_TAGS),
  ...Object.keys(SLIDE_RULE_REASON_TAGS),
  "hesitate",
]);

export type Timing = {
  shown_at?: string;
  first_touch_at?: string;
  decided_at?: string;
  sent_at?: string;
  read_ms?: number;
  edit_ms?: number;
  voice_sec?: number;
};

export type VoiceSegment = {
  target?: string;
  line?: number | null;
  t_start?: number;
  t_end?: number;
  text: string;
  vague?: boolean; // 「ここ／これ」を含む（後で確認）
};

export type DecisionInput = {
  surface: string;
  action: string;
  source: string;
  targetType: string;
  targetId: string;
  employee?: string | null;
  subject?: string | null;
  partner?: string | null;
  lane?: string | null;
  aiProposal?: string | null;
  finalText?: string | null;
  note?: string | null;
  /** 同じ判断の再送を1行にまとめる鍵。クライアントが判断ごとに1つ作る */
  idemKey?: string | null;
  reasonTags?: string[];
  scope?: string | null;
  quality?: string | null;
  stayReason?: string | null;
  nextStep?: string | null;
  appliedRules?: string[];
  timing?: Timing;
  voice?: { segments: VoiceSegment[] } | null;
  payload?: Record<string, unknown>;
};

export type DecisionRow = {
  surface: string;
  action: string;
  source: string;
  employee: string | null;
  target_type: string;
  target_id: string;
  subject: string | null;
  partner: string | null;
  lane: string | null;
  ai_proposal: string | null;
  final_text: string | null;
  edited: boolean | null;
  note: string | null;
  payload: Record<string, unknown>;
};

const SURFACE_SET = new Set<string>(SURFACES);
const SOURCE_SET = new Set<string>(SOURCES);
const ACTION_SET = new Set<string>(ACTIONS);

function cut(s: unknown, n: number): string | null {
  if (s === null || s === undefined) return null;
  const t = String(s).trim();
  return t ? t.slice(0, n) : null;
}

function isoOrNull(s: unknown): string | null {
  if (typeof s !== "string" || !s) return null;
  const t = Date.parse(s);
  return Number.isFinite(t) ? new Date(t).toISOString() : null;
}

function nonNegInt(n: unknown): number | null {
  const v = Number(n);
  return Number.isFinite(v) && v >= 0 ? Math.round(v) : null;
}

/** 下書きから送った文までの直しの割合（0=そのまま, 1=全部書き換え）。文字単位の編集距離 */
export function editRatio(before: string | null | undefined, after: string | null | undefined): number | null {
  if (before === null || before === undefined || after === null || after === undefined) return null;
  const a = String(before);
  const b = String(after);
  if (a === b) return 0;
  const n = Math.max(a.length, b.length);
  if (!n) return 0;
  // 長文で重くならないよう 4000 字で打ち切る
  const x = a.slice(0, 4000);
  const y = b.slice(0, 4000);
  let prev = new Array<number>(y.length + 1);
  for (let j = 0; j <= y.length; j++) prev[j] = j;
  for (let i = 1; i <= x.length; i++) {
    const cur = new Array<number>(y.length + 1);
    cur[0] = i;
    for (let j = 1; j <= y.length; j++) {
      const c = x.charCodeAt(i - 1) === y.charCodeAt(j - 1) ? 0 : 1;
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + c);
    }
    prev = cur;
  }
  return Math.round((prev[y.length] / Math.max(x.length, y.length)) * 1000) / 1000;
}

/** 判断にかかった時間（表示から判断まで）。取れなければ null */
export function decideMs(t: Timing | undefined): number | null {
  if (!t) return null;
  const a = isoOrNull(t.shown_at);
  const b = isoOrNull(t.decided_at);
  if (!a || !b) return null;
  const ms = Date.parse(b) - Date.parse(a);
  // 6時間を超えるのは開きっぱなし。数えない
  return ms >= 0 && ms <= 6 * 3600_000 ? ms : null;
}

/** 鍵がないときの代わり（同じ分のうちに同じ物へ同じ判断＝同じ判断とみなす） */
export function fallbackIdemKey(i: Pick<DecisionInput, "surface" | "action" | "source" | "targetId">, at: Date): string {
  const minute = Math.floor(at.getTime() / 60_000);
  return `${i.source}:${i.surface}:${i.targetId}:${i.action}:${minute}`;
}

function cleanTags(tags: unknown): { tags: string[]; unknown: string[] } {
  if (!Array.isArray(tags)) return { tags: [], unknown: [] };
  const out: string[] = [];
  const unk: string[] = [];
  for (const raw of tags) {
    const t = String(raw || "").trim();
    if (!t || out.includes(t)) continue;
    if (KNOWN_TAGS.has(t)) out.push(t);
    else unk.push(t.slice(0, 40));
  }
  return { tags: out.slice(0, 6), unknown: unk.slice(0, 6) };
}

function cleanVoice(v: DecisionInput["voice"]): { segments: VoiceSegment[] } | null {
  if (!v || !Array.isArray(v.segments) || !v.segments.length) return null;
  const segments = v.segments.slice(0, 60).map((s) => {
    const text = String(s.text || "").slice(0, 1000);
    return {
      target: cut(s.target, 200) || undefined,
      line: s.line === null || s.line === undefined ? null : nonNegInt(s.line),
      t_start: nonNegInt(s.t_start) ?? undefined,
      t_end: nonNegInt(s.t_end) ?? undefined,
      text,
      vague: /ここ|これ|それ|あれ/.test(text) || undefined,
    } as VoiceSegment;
  });
  return { segments: segments.filter((s) => s.text) };
}

export type Normalized = { ok: true; row: DecisionRow; idemKey: string } | { ok: false; error: string };

/**
 * 入口の形を owner_decisions の1行に揃える。
 * 知らない surface / source / action は弾く（記録が散らばると週次で数えられないため）。
 */
export function normalizeDecision(i: DecisionInput, now: Date = new Date()): Normalized {
  const surface = String(i.surface || "").trim();
  const action = String(i.action || "").trim();
  const rawSource = String(i.source || "").trim();
  const source = coarseSource(rawSource) || rawSource;
  if (!SURFACE_SET.has(surface)) return { ok: false, error: `unknown surface: ${surface || "(empty)"}` };
  if (!ACTION_SET.has(action)) return { ok: false, error: `unknown action: ${action || "(empty)"}` };
  if (!SOURCE_SET.has(source)) return { ok: false, error: `unknown source: ${source || "(empty)"}` };
  const targetType = cut(i.targetType, 60);
  if (!targetType) return { ok: false, error: "targetType required" };
  const targetId = cut(i.targetId, 200) || "-";

  const idemKey = cut(i.idemKey, 200) || fallbackIdemKey({ surface, action, source, targetId }, now);
  const { tags, unknown } = cleanTags(i.reasonTags);

  const aiProposal = cut(i.aiProposal, 4000);
  const finalText = cut(i.finalText, 8000);
  const ratio = editRatio(aiProposal, finalText);

  const timing: Record<string, unknown> = {};
  if (i.timing) {
    for (const k of ["shown_at", "first_touch_at", "decided_at", "sent_at"] as const) {
      const v = isoOrNull(i.timing[k]);
      if (v) timing[k] = v;
    }
    for (const k of ["read_ms", "edit_ms", "voice_sec"] as const) {
      const v = nonNegInt(i.timing[k]);
      if (v !== null) timing[k] = v;
    }
  }
  const dms = decideMs(i.timing);

  const scope = i.scope && (SCOPES as readonly string[]).includes(i.scope) ? i.scope : null;
  const quality = i.quality && (QUALITY as readonly string[]).includes(i.quality) ? i.quality : null;
  const stay = i.stayReason && i.stayReason in STAY_REASON_TAGS ? i.stayReason : null;
  const voice = cleanVoice(i.voice);
  const applied = Array.isArray(i.appliedRules)
    ? Array.from(new Set(i.appliedRules.map((r) => String(r).trim()).filter(Boolean))).slice(0, 20)
    : [];

  // 呼び出し側の payload を先に、契約のキーを後に（契約が勝つ）
  const payload: Record<string, unknown> = { ...(i.payload || {}) };
  payload.v = CONTRACT_VERSION;
  payload.idem_key = idemKey;
  payload.outcome = outcomeOf(action);
  if (rawSource && rawSource !== source) payload.source_detail = rawSource.slice(0, 60);
  if (tags.length) payload.reason_tags = tags;
  if (unknown.length) payload.reason_tags_unknown = unknown;
  if (scope) payload.scope = scope;
  if (quality) payload.quality = quality;
  if (stay) payload.stay_reason = stay;
  if (i.nextStep) payload.next_step = String(i.nextStep).slice(0, 500);
  if (applied.length) payload.applied_rules = applied;
  if (ratio !== null) payload.edit_ratio = ratio;
  if (Object.keys(timing).length) payload.timing = timing;
  if (dms !== null) payload.decide_ms = dms;
  if (voice && voice.segments.length) payload.voice = voice;

  return {
    ok: true,
    idemKey,
    row: {
      surface,
      action,
      source,
      employee: cut(i.employee, 40),
      target_type: targetType,
      target_id: targetId,
      subject: cut(i.subject, 500),
      partner: cut(i.partner, 200),
      lane: cut(i.lane, 40),
      ai_proposal: aiProposal,
      final_text: finalText,
      edited: ratio === null ? null : ratio > 0,
      note: cut(i.note, 2000),
      payload,
    },
  };
}

/** 週の始まり（月曜 0:00 JST）を UTC ISO で */
export function weekStartIso(now: Date = new Date()): string {
  const jst = new Date(now.getTime() + 9 * 3600_000);
  const dow = (jst.getUTCDay() + 6) % 7; // 月=0
  const startJst = Date.UTC(jst.getUTCFullYear(), jst.getUTCMonth(), jst.getUTCDate() - dow);
  return new Date(startJst - 9 * 3600_000).toISOString();
}

export type WeekTally = { take: number; ng: number; hesitate: number; none: number; later: number; note: number; total: number };

/** 今週のログの粒（採った／見送った／迷った／未判断…）を数える */
export function tally(rows: { action: string; payload?: Record<string, unknown> | null }[]): WeekTally {
  const t: WeekTally = { take: 0, ng: 0, hesitate: 0, none: 0, later: 0, note: 0, total: 0 };
  for (const r of rows) {
    const o = (r.payload && typeof r.payload.outcome === "string" ? r.payload.outcome : outcomeOf(r.action)) as Outcome;
    if (o in t) t[o] += 1;
    t.total += 1;
  }
  return t;
}
