/** Quiet Edge Phase 3 — Journal 欠落・異常検知と問い生成 */

/** 観察用の改善目標（診断ではない）。
 * AutoSnore 公式閾値は非公開のため、同種 SnoreLab の「≤10」を参照。
 */
export const SNORE_SCORE_TARGET = 10;

export type JournalDailyRow = {
  recorded_at: string;
  excerpt: string;
  char_count: number;
  source: string;
  sleep_signal?: string | null;
  sleep_tags?: string[] | null;
};

/** Journal から睡眠関連タグを推定（DB未同期時のフォールバック） */
export function inferJournalSleepTags(
  excerpt: string,
  signal?: string | null,
): string[] {
  const blob = `${signal || ""}\n${excerpt || ""}`;
  const tags: string[] = [];
  if (blob.includes("夜の防衛線")) tags.push("defense_line");
  if (/達成（〇）|就寝達成|達成\(〇\)/.test(blob)) tags.push("bedtime_ok");
  if (/就寝超過|超過（×）|24:00超過|就寝未定|遅延|未達成/.test(blob)) {
    tags.push("bedtime_late");
  }
  if (/飲酒|ワイン|ビール|飲み会/.test(blob)) tags.push("alcohol");
  if (/鼻|鼻づまり|花粉症/.test(blob)) tags.push("nasal");
  if (/残業|深夜作業|深追い|没頭/.test(blob)) tags.push("late_work");
  if (/疲れ|疲労|爆睡|猛烈な眠気/.test(blob)) tags.push("fatigue");
  return [...new Set(tags)];
}

export const SLEEP_TAG_LABELS: Record<string, string> = {
  defense_line: "防衛線あり",
  bedtime_ok: "就寝達成",
  bedtime_late: "就寝遅れ",
  alcohol: "飲酒言及",
  nasal: "鼻・詰まり",
  late_work: "遅夜作業",
  fatigue: "疲労",
};

export type ContextNoteRow = {
  id: number;
  recorded_at: string;
  trigger: string;
  prompt: string;
  answer: string;
  source: string;
  created_at: string;
};

export type SnoreLite = {
  recorded_at: string;
  score: number;
  count: number | null;
};

export type VitalLite = {
  recorded_at: string;
  metric: string;
  value: number;
};

export type QuietEdgeAsk = {
  recorded_at: string;
  trigger: string;
  prompt: string;
  reason: string;
};

export function ymdJst(d: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(d);
}

export function monthKeyJst(d: Date = new Date()): string {
  return ymdJst(d).slice(0, 7);
}

/** YYYY-MM を delta 月ずらす（JST の暦月想定） */
export function shiftMonthYm(ym: string, delta: number): string {
  const [y, m] = ym.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1 + delta, 1));
  return `${dt.getUTCFullYear()}-${String(dt.getUTCMonth() + 1).padStart(2, "0")}`;
}

/** 月次レビューの既定対象: 今日(JST)の前月（例: 2026-08-08 → 2026-07） */
export function defaultMonthlyReviewYm(d: Date = new Date()): string {
  return shiftMonthYm(monthKeyJst(d), -1);
}

export function addDaysYmd(ymd: string, delta: number): string {
  const [y, m, d] = ymd.split("-").map(Number);
  const dt = new Date(Date.UTC(y, m - 1, d));
  dt.setUTCDate(dt.getUTCDate() + delta);
  return dt.toISOString().slice(0, 10);
}

function daysBetweenYmd(a: string, b: string): number {
  const [ay, am, ad] = a.split("-").map(Number);
  const [by, bm, bd] = b.split("-").map(Number);
  const ta = Date.UTC(ay, am - 1, ad);
  const tb = Date.UTC(by, bm - 1, bd);
  return Math.round((tb - ta) / (1000 * 60 * 60 * 24));
}

/** 直近 N 日で Journal 欠落・いびき急変を拾い、未回答の問いを返す */
export function buildQuietEdgeAsks(input: {
  journals: JournalDailyRow[];
  notes: ContextNoteRow[];
  snore: SnoreLite[];
  vitals?: VitalLite[];
  windowDays?: number;
  maxAsks?: number;
}): QuietEdgeAsk[] {
  const windowDays = input.windowDays ?? 14;
  const maxAsks = input.maxAsks ?? 5;
  const today = ymdJst(new Date());
  const start = addDaysYmd(today, -(windowDays - 1));

  const journalByDay = new Map(
    input.journals.map((j) => [j.recorded_at, j] as const),
  );
  const answered = new Set(
    input.notes
      .filter((n) => n.answer && n.answer.trim().length > 0)
      .map((n) => `${n.recorded_at}|${n.trigger}`),
  );

  const snoreSorted = [...input.snore]
    .filter((s) => s.recorded_at >= start && s.recorded_at <= today)
    .sort((a, b) => a.recorded_at.localeCompare(b.recorded_at));

  const asks: QuietEdgeAsk[] = [];

  // 1) Journal 欠落 — いびき記録がある日だけ（無関係な空白日は聞かない）
  const snoreDays = new Set(snoreSorted.map((s) => s.recorded_at));
  for (let i = 0; i < windowDays; i++) {
    const d = addDaysYmd(start, i);
    if (d >= today) continue; // 今日は書いている最中かも
    if (!snoreDays.has(d)) continue;
    const j = journalByDay.get(d);
    const thin = !j || !j.excerpt.trim() || j.char_count < 40;
    if (!thin) continue;
    const trigger = "missing_journal";
    if (answered.has(`${d}|${trigger}`)) continue;
    asks.push({
      recorded_at: d,
      trigger,
      reason: "いびき記録あり・Journal 薄い／なし",
      prompt: `${d} はいびき記録がありますが Journal が薄いです。その夜〜朝、何がありましたか？（飲酒・残業・鼻詰まり・旅行など短くでOK）`,
    });
  }

  // 1b) Journal に就寝遅れがあり、いびきも悪い日 → 要因確認
  for (const s of snoreSorted) {
    if (s.recorded_at >= today) continue;
    const j = journalByDay.get(s.recorded_at);
    if (!j) continue;
    const tags =
      j.sleep_tags && j.sleep_tags.length
        ? j.sleep_tags
        : inferJournalSleepTags(j.excerpt, j.sleep_signal);
    if (!tags.includes("bedtime_late") && !tags.includes("alcohol")) continue;
    if (Number(s.score) < 30 && (s.count == null || s.count < 200)) continue;
    const trigger = "journal_lifestyle";
    if (answered.has(`${s.recorded_at}|${trigger}`)) continue;
    const signal = (j.sleep_signal || "").trim();
    asks.push({
      recorded_at: s.recorded_at,
      trigger,
      reason: tags.includes("alcohol")
        ? "Journalに飲酒言及＋いびき高め"
        : "Journalに就寝遅れ＋いびき高め",
      prompt: `${s.recorded_at} は Journal（${signal || tags.join(",")}）といびきスコア ${Number(s.score).toFixed(1)} が重なっています。その夜、他に思い当たることはありますか？`,
    });
  }

  // 2) いびき急変 — カレンダー上 1〜2 日以内の連続比較のみ（欠測明けの戻りを悪化と誤認しない）
  for (let i = 1; i < snoreSorted.length; i++) {
    const prev = snoreSorted[i - 1];
    const cur = snoreSorted[i];
    const gap = daysBetweenYmd(prev.recorded_at, cur.recorded_at);
    if (gap < 1 || gap > 2) continue;
    const scoreJump = Number(cur.score) - Number(prev.score) >= 15;
    const countJump =
      prev.count != null &&
      cur.count != null &&
      prev.count > 0 &&
      cur.count / prev.count >= 1.6 &&
      cur.count - prev.count >= 20;
    if (!scoreJump && !countJump) continue;
    const trigger = "snore_spike";
    if (answered.has(`${cur.recorded_at}|${trigger}`)) continue;
    const deltaLabel = scoreJump
      ? `スコア ${Number(prev.score).toFixed(1)}→${Number(cur.score).toFixed(1)}`
      : `回数 ${prev.count}→${cur.count}`;
    asks.push({
      recorded_at: cur.recorded_at,
      trigger,
      reason: deltaLabel,
      prompt: `${cur.recorded_at} のいびきが直近より悪化しています（${deltaLabel}）。その夜、何がありましたか？`,
    });
  }

  // 優先: spike → missing journal（いびきあり）
  const rank = (a: QuietEdgeAsk) => (a.trigger === "snore_spike" ? 0 : 1);
  asks.sort((a, b) => {
    const r = rank(a) - rank(b);
    if (r !== 0) return r;
    return b.recorded_at.localeCompare(a.recorded_at);
  });

  // 同日は1つに抑制
  const seenDay = new Set<string>();
  const out: QuietEdgeAsk[] = [];
  for (const a of asks) {
    if (seenDay.has(a.recorded_at)) continue;
    seenDay.add(a.recorded_at);
    out.push(a);
    if (out.length >= maxAsks) break;
  }
  return out;
}
