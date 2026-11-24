/**
 * まとめて判断（/all）の部品。メール・片付け・お題をジャンルをまたいで1つの一覧にする。
 * - 重要度（高=3／中=2／低=1）を付けて、重要な順に並べる
 * - 提案（AIのおすすめ）がある行は、そのまま採用できる
 * 記録先・反映はジャンルごとの既存の道（/api/desk/decide・/api/cleanup・/api/decide）をそのまま使う。
 * ここは「見せ方と仕分け」だけで、Todoist やメールを直接変えない。
 */
import type { DeskCard } from "./deskCore.ts";
import type { CleanupCard } from "./cleanupBulk.ts";
import type { SeedTopic } from "./seed312.ts";

export type Genre = "mail" | "cleanup" | "topic";
export type Level = 1 | 2 | 3;

export const GENRE_LABEL: Record<Genre, string> = { mail: "メール", cleanup: "片付け", topic: "お題" };
export const LEVEL_LABEL: Record<Level, string> = { 3: "高", 2: "中", 1: "低" };

/** どのジャンルにも置く「あとで」。メール=迷う／片付け=残す／お題=保留 */
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
  /** AIのおすすめ（options の act）。無ければ null */
  suggest: string | null;
  why: string;
  options: AllOption[];
  /** 1件ずつ開く先（返信など、ここでは決めないもの） */
  link?: string;
  /** お題の記録に要るもの（お題のときだけ） */
  topic?: { text: string; proposals: { index: number; label: string; body: string }[] };
  /** 判断ログに添える（メール: 相手・種別。片付けの記録に使う元カード） */
  cleanup?: CleanupCard;
  mail?: { partner: string; lane: string };
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

function daysUntil(iso: string | null | undefined, today: string): number | null {
  if (!iso || !/^\d{4}-\d{2}-\d{2}/.test(iso)) return null;
  return Math.round((Date.parse(iso.slice(0, 10)) - Date.parse(today)) / 86400000);
}

export function cleanupItem(c: CleanupCard, today: string): AllItem {
  const dl = daysUntil(c.deadline, today);
  const urgent = (dl !== null && dl <= 7) || highPriority(c.priority);
  const level: Level = urgent ? 3 : c.suggest === "keep" ? 2 : 1;
  const act = c.suggest === "keep" ? LATER : c.suggest;
  return {
    key: `cleanup:${c.id}`,
    genre: "cleanup",
    id: c.id,
    title: c.title,
    sub: [c.origin === "318" ? "318判断依頼" : "", c.sender, c.age_days != null ? `${c.age_days}日前` : ""].filter(Boolean).join("｜"),
    summary: c.summary,
    level,
    rank: dl !== null ? 1000 - dl : c.age_days ?? 0,
    suggest: act,
    why: c.why,
    options: [
      { act: "close", label: "完了" },
      { act: "drop", label: "削除" },
      { act: LATER, label: "残す" },
    ],
    link: c.gmail_url || undefined,
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
    suggest: t.starred ? `pick:${t.starred}` : null,
    why: t.starred ? "AIの推しの案あり" : "案から選ぶ",
    options,
    link: `/312?topic=${encodeURIComponent(t.id)}`,
    topic: { text: t.topicText, proposals: t.proposals },
  };
}

/** 重要度の高い順 → 同じ重要度の中は rank の大きい順 → ジャンル順 */
export function sortItems(items: AllItem[]): AllItem[] {
  const g: Genre[] = ["mail", "cleanup", "topic"];
  return [...items].sort(
    (a, b) => b.level - a.level || b.rank - a.rank || g.indexOf(a.genre) - g.indexOf(b.genre) || a.key.localeCompare(b.key),
  );
}

export function optionLabel(it: AllItem, act: string): string {
  return it.options.find((o) => o.act === act)?.label ?? act;
}

export type Filter = { genre: Genre | "all"; level: Level | 0 };

export function applyFilter(items: AllItem[], f: Filter): AllItem[] {
  return items.filter((i) => (f.genre === "all" || i.genre === f.genre) && (f.level === 0 || i.level === f.level));
}

/** 「提案どおり」を、まだ選んでいない行に入れる（選び直しは上書きしない） */
export function adoptSuggestions(items: AllItem[], chosen: Record<string, string>): Record<string, string> {
  const out = { ...chosen };
  for (const i of items) if (i.suggest && !out[i.key]) out[i.key] = i.suggest;
  return out;
}

export function countBy(items: AllItem[]) {
  const genre: Record<Genre, number> = { mail: 0, cleanup: 0, topic: 0 };
  const level: Record<Level, number> = { 1: 0, 2: 0, 3: 0 };
  for (const i of items) {
    genre[i.genre] += 1;
    level[i.level] += 1;
  }
  return { genre, level, total: items.length };
}
