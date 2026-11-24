/**
 * まとめて判断（/all）の部品。判断の入口（ジャンル）をまたいで1つの一覧にする。
 * - ジャンル: メール／318 要判断／313 週の整理／スター片付け／お題／今週の9件／Zaim／ルール候補
 * - 重要度（高=3／中=2／低=1）・期日超過の日数・判断の重さ（すぐ決まる／じっくり）で並べ替え・絞り込み
 * - 提案（AIのおすすめ）がある行は、そのまま採用できる（行ごと・チェックした分・表示中ぜんぶ）
 * 記録先・反映はジャンルごとの既存の道（/api/desk/decide・/api/cleanup・/api/decide・/api/zaim・/api/rules/decide）をそのまま使う。
 * ここは「見せ方と仕分け」だけで、Todoist やメールを直接変えない。
 * Todoist の削除はここでは選べない（スター片付けの「削除」は /313/bulk だけ。313 の「やめる」は完了扱いで削除しない）。
 */
import type { DeskCard } from "./deskCore.ts";
import type { CleanupCard } from "./cleanupBulk.ts";
import type { SeedTopic } from "./seed312.ts";
import type { ZaimFix } from "./zaimCore.ts";
import type { RuleCandidate } from "./rules.ts";
import type { Snapshot as WeekSnapshot, Weight } from "./weekPick.ts";

export type Genre = "mail" | "g318" | "g313" | "star" | "topic" | "week" | "zaim" | "rule";
export type Level = 1 | 2 | 3;

/** 表示とバッジの順 */
export const GENRES: Genre[] = ["mail", "g318", "g313", "star", "topic", "week", "zaim", "rule"];

export const GENRE_LABEL: Record<Genre, string> = {
  mail: "メール",
  g318: "318 要判断",
  g313: "313 週の整理",
  star: "スター片付け",
  topic: "お題",
  week: "今週の9件",
  zaim: "Zaim",
  rule: "ルール候補",
};
export const LEVEL_LABEL: Record<Level, string> = { 3: "高", 2: "中", 1: "低" };
export const WEIGHT_MARK: Record<Weight, string> = { quick: "すぐ", deep: "じっくり", unknown: "" };

/** 「あとで」。メール=迷う／片付け=残す／お題=保留 */
export const LATER = "later";

export type AllOption = { act: string; label: string };

export type AllItem = {
  key: string;
  genre: Genre;
  id: string;
  title: string;
  sub: string;
  summary: string;
  level: Level;
  /** 同じ重要度の中の並び（大きいほど先） */
  rank: number;
  /** 期日（締切）を過ぎた日数。過ぎていなければ 0 以下、期日なしは null */
  overdue: number | null;
  /** 判断の重さ（今週の9件の材料で分かる件だけ。基準は config/todoist_weekly_weight.yaml） */
  weight?: Weight;
  weightWhy?: string;
  /** AIのおすすめ（options の act）。無ければ null */
  suggest: string | null;
  why: string;
  /** その場で選べるもの。空なら「開いて決める」行（今週の9件など） */
  options: AllOption[];
  /** 1件ずつ開く先 */
  link?: string;
  topic?: { text: string; proposals: { index: number; label: string; body: string }[] };
  cleanup?: CleanupCard;
  mail?: { partner: string; lane: string };
  rule?: RuleCandidate;
};

const PAY_FAIL_RE = /(未済|ご利用いただけませんでした|決済(が)?(失敗|エラー)|引き?落とし(が)?(でき|され)ませんでした|振替不能|残高不足)/;

export function mailItem(c: DeskCard): AllItem {
  const pay = PAY_FAIL_RE.test(c.subject);
  const level: Level = c.lane === "partner" || pay ? 3 : c.postedToSlack || c.hesitatedAt || (c.score ?? 0) > 0 ? 2 : 1;
  const why = pay ? "支払いの失敗" : c.lane === "partner" ? "パートナーからの連絡" : c.postedToSlack ? "Slackで要対応に出したメール" : c.hesitatedAt ? "前に迷ったメール" : "人が書いたメール";
  return {
    key: `mail:${c.id}`,
    genre: "mail",
    id: c.id,
    title: c.subject,
    sub: [c.who, c.receivedAt ? c.receivedAt.slice(5, 10).replace("-", "/") : ""].filter(Boolean).join("｜"),
    summary: c.summary,
    level,
    rank: c.score ?? 0,
    overdue: null,
    suggest: null,
    why,
    options: [
      { act: "todo", label: "ToDoにする" },
      { act: "done", label: "済み" },
      { act: "skip", label: "見送る" },
      { act: LATER, label: "あとで" },
    ],
    link: `/desk?surface=triage&item=${encodeURIComponent(c.id)}`,
    mail: { partner: c.who, lane: c.lane },
  };
}

function highPriority(p: unknown): boolean {
  if (typeof p === "number") return p >= 3; // Todoist API は 4=p1 / 3=p2
  return /^p[12]$/i.test(String(p ?? ""));
}

export function daysUntil(iso: string | null | undefined, today: string): number | null {
  if (!iso || !/^\d{4}-\d{2}-\d{2}/.test(iso)) return null;
  return Math.round((Date.parse(iso.slice(0, 10)) - Date.parse(today)) / 86400000);
}

export type WeightMap = Map<string, { weight: Weight; why: string }>;

/** 今週の9件の材料（snapshot）から、タスク id → 判断の重さ */
export function weightMap(snap: Pick<WeekSnapshot, "candidates"> | null | undefined): WeightMap {
  const m: WeightMap = new Map();
  for (const c of snap?.candidates || []) if (c.weight && c.weight !== "unknown") m.set(String(c.id), { weight: c.weight, why: c.weight_why || "" });
  return m;
}

export function cleanupItem(c: CleanupCard, today: string, weights?: WeightMap): AllItem {
  const genre: Genre = c.origin === "318" ? "g318" : c.origin === "313" ? "g313" : "star";
  const dl = daysUntil(c.deadline || c.due, today);
  const urgent = (dl !== null && dl <= 7) || highPriority(c.priority);
  const level: Level = urgent ? 3 : c.suggest === "keep" || genre === "g318" ? 2 : 1;
  let options: AllOption[];
  let suggest: string | null;
  let why = c.why;
  if (genre === "g313") {
    // 313 週の整理: 済み・やめる・残す だけ。やめるも完了扱い（削除しない）
    options = [
      { act: "close", label: "済み" },
      { act: "drop", label: "やめる" },
      { act: LATER, label: "残す" },
    ];
    suggest = c.suggest === "keep" ? LATER : c.suggest;
  } else {
    // 318・スター: ここでは削除を出さない（削除は /313/bulk で1件ずつ）
    options = [
      { act: "close", label: "完了" },
      { act: LATER, label: "残す" },
    ];
    suggest = c.suggest === "keep" ? LATER : c.suggest === "close" ? "close" : null;
    if (c.suggest === "drop") why = `${c.why}（おすすめは削除。削除はここでは選べないので「片付けを開く」から）`;
  }
  const w = weights?.get(String(c.id));
  return {
    key: `cleanup:${c.id}`,
    genre,
    id: c.id,
    title: c.title,
    sub: [c.sender, c.age_days != null ? `${c.age_days}日前` : "", c.prev || ""].filter(Boolean).join("｜"),
    summary: c.summary,
    level,
    rank: dl !== null ? 1000 - dl : c.age_days ?? 0,
    overdue: dl === null ? null : -dl,
    weight: w?.weight,
    weightWhy: w?.why,
    suggest,
    why,
    options,
    link: c.evidence_url || c.gmail_url || "/313/bulk",
    cleanup: c,
  };
}

export function topicItem(t: SeedTopic): AllItem {
  const options: AllOption[] = t.proposals.map((p) => ({ act: `pick:${p.index}`, label: `案${p.index} ${p.label}` }));
  options.push({ act: LATER, label: "保留" });
  return {
    key: `topic:${t.id}`,
    genre: "topic",
    id: t.id,
    title: t.topicText.replace(/^\[[^\]]*\]\s*/, "").split("\n")[0].slice(0, 80),
    sub: "新規起票のお題",
    summary: t.starred ? `おすすめ: 案${t.starred} ${t.proposals.find((p) => p.index === t.starred)?.label ?? ""}` : "",
    level: 2,
    rank: 0,
    overdue: null,
    suggest: t.starred ? `pick:${t.starred}` : null,
    why: t.starred ? "AIの推しの案あり" : "案から選ぶ",
    options,
    link: `/312?topic=${encodeURIComponent(t.id)}`,
    topic: { text: t.topicText, proposals: t.proposals },
  };
}

/**
 * 今週の9件: 週の確定はカレンダーに置く判断なので、ここでは1行の「開いて決める」だけ（その場のボタンは出さない）。
 * 材料が無い・その週を確定済みなら出さない。週の始まり（月曜）まで2日以内なら重要度「高」。
 */
export function weekItem(snap: WeekSnapshot | null | undefined, committed: boolean, today: string): AllItem | null {
  if (!snap?.week || committed) return null;
  const until = daysUntil(snap.week, today);
  const n: Record<Weight, number> = { quick: 0, deep: 0, unknown: 0 };
  for (const c of snap.candidates || []) n[c.weight || "unknown"] += 1;
  return {
    key: `week:${snap.week}`,
    genre: "week",
    id: snap.week,
    title: `${snap.week.slice(5).replace("-", "/")} からの週の9件が未確定`,
    sub: `候補 ${(snap.candidates || []).length}件${(snap.inlet || []).length ? `・入口の話題 ${(snap.inlet || []).length}件` : ""}`,
    summary: `すぐ決まる ${n.quick}／じっくり ${n.deep}／未判別 ${n.unknown}`,
    level: until !== null && until <= 2 ? 3 : 2,
    rank: until !== null ? 1000 - until : 0,
    overdue: until === null ? null : -until,
    suggest: null,
    why: "月・水・金に置いて確定（カレンダーで決めるので開いて行う）",
    options: [],
    link: "/week",
  };
}

export function zaimItem(f: ZaimFix): AllItem {
  return {
    key: `zaim:${f.id}`,
    genre: "zaim",
    id: f.id,
    title: f.proposal || "費目の直し",
    sub: [f.shop, f.at ? f.at.slice(5, 10).replace("-", "/") : ""].filter(Boolean).join("｜"),
    summary: "",
    level: 1,
    rank: 0,
    overdue: null,
    weight: "quick",
    weightWhy: "正しい／違うの1タップ",
    suggest: null,
    why: "学習で直した費目の確認",
    options: [
      { act: "good", label: "正しい" },
      { act: "wrong", label: "違う" },
    ],
    link: "/zaim",
  };
}

export function ruleItem(c: RuleCandidate): AllItem {
  return {
    key: `rule:${c.id}`,
    genre: "rule",
    id: c.id,
    title: c.text || c.rule_line,
    sub: [c.employee ? `社員 ${c.employee}` : "", c.status === "hypothesis" ? "仮説" : "候補"].filter(Boolean).join("｜"),
    summary: c.rule_line && c.rule_line !== c.text ? c.rule_line : "",
    level: 2,
    rank: (c.evidence || []).length,
    overdue: null,
    // 基準は本人が選ぶもの。AI のおすすめは置かない（提案どおりの一括に入らない）
    suggest: null,
    why: c.why || "判断ログから見つけたルール候補",
    options: [
      { act: "accept", label: "採用" },
      { act: "once", label: "今回だけ" },
      { act: "reject", label: "違う" },
    ],
    link: "/rules",
    rule: c,
  };
}

export type SortMode = "level" | "overdue" | "quick";
export const SORT_LABEL: Record<SortMode, string> = { level: "重要度順", overdue: "期日超過順", quick: "すぐ決まる順" };

const WEIGHT_ORDER: Record<string, number> = { quick: 0, unknown: 1, deep: 2 };

function byLevel(a: AllItem, b: AllItem): number {
  return b.level - a.level || b.rank - a.rank || GENRES.indexOf(a.genre) - GENRES.indexOf(b.genre) || a.key.localeCompare(b.key);
}

/**
 * level: 重要度の高い順 → rank → ジャンル順
 * overdue: 期日を過ぎた日数の多い順（期日なしは後ろ）→ 重要度
 * quick: すぐ決まる → 提案あり → 未判別 → じっくり、その中は重要度（時間がない時に早く片付く順）
 */
export function sortItems(items: AllItem[], mode: SortMode = "level"): AllItem[] {
  const list = [...items];
  if (mode === "overdue") return list.sort((a, b) => (b.overdue ?? -Infinity) - (a.overdue ?? -Infinity) || byLevel(a, b));
  if (mode === "quick") {
    const q = (i: AllItem) => (i.weight === "quick" ? 0 : i.weight === "deep" ? 3 : i.suggest ? 1 : 2) + (i.options.length ? 0 : 4);
    return list.sort((a, b) => q(a) - q(b) || WEIGHT_ORDER[a.weight || "unknown"] - WEIGHT_ORDER[b.weight || "unknown"] || byLevel(a, b));
  }
  return list.sort(byLevel);
}

export function optionLabel(it: AllItem, act: string): string {
  return it.options.find((o) => o.act === act)?.label ?? act;
}

export type Filter = { genre: Genre | "all"; level: Level | 0; weight?: Weight | "all"; suggestOnly?: boolean };

export function applyFilter(items: AllItem[], f: Filter): AllItem[] {
  return items.filter(
    (i) =>
      (f.genre === "all" || i.genre === f.genre) &&
      (f.level === 0 || i.level === f.level) &&
      (!f.weight || f.weight === "all" || i.weight === f.weight) &&
      (!f.suggestOnly || !!i.suggest),
  );
}

/** 「提案どおり」を、まだ選んでいない行に入れる（選び直しは上書きしない）。only を渡すとその行だけ */
export function adoptSuggestions(items: AllItem[], chosen: Record<string, string>, only?: Set<string>): Record<string, string> {
  const out = { ...chosen };
  for (const i of items) if (i.suggest && !out[i.key] && (!only || only.has(i.key))) out[i.key] = i.suggest;
  return out;
}

export function countBy(items: AllItem[]) {
  const genre = Object.fromEntries(GENRES.map((g) => [g, 0])) as Record<Genre, number>;
  const level: Record<Level, number> = { 1: 0, 2: 0, 3: 0 };
  const weight: Record<Weight, number> = { quick: 0, deep: 0, unknown: 0 };
  let suggest = 0;
  let overdue = 0;
  for (const i of items) {
    genre[i.genre] += 1;
    level[i.level] += 1;
    weight[i.weight || "unknown"] += 1;
    if (i.suggest) suggest += 1;
    if ((i.overdue ?? 0) > 0) overdue += 1;
  }
  return { genre, level, weight, suggest, overdue, total: items.length };
}

/** 片付け（318・313・スター）か。記録は /api/cleanup に1回でまとめて送る */
export function isCleanup(i: Pick<AllItem, "genre">): boolean {
  return i.genre === "g318" || i.genre === "g313" || i.genre === "star";
}

/**
 * 片付けの選択 → cleanupBulk の Choice。ここで選べない処置（313 以外の削除・日を変える）は落とす。
 * 戻り値 null は「送らない」。
 */
export function cleanupChoice(i: AllItem, act: string): { act: "close" | "drop" | "keep" } | null {
  if (!isCleanup(i)) return null;
  if (act === LATER) return { act: "keep" };
  if (act === "close") return { act: "close" };
  if (act === "drop" && i.genre === "g313") return { act: "drop" };
  return null;
}
