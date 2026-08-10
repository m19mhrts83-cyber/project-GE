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
  source?: string;
};

export type QuietEdgeAsk = {
  recorded_at: string;
  trigger: string;
  prompt: string;
  reason: string;
};

export type TreatmentLite = {
  session_no: number;
  scheduled_at: string | null;
  status: string;
  label?: string | null;
};

/** 治療イベントの実施日（JST 暦日） */
export function treatmentYmdJst(scheduledAt: string | null | undefined): string | null {
  if (!scheduledAt) return null;
  const t = new Date(scheduledAt);
  if (!Number.isFinite(t.getTime())) return null;
  return ymdJst(t);
}

/** グラフ用: 完了セッションから治療当日／直後（既定+1〜+2日）を付与。
 * 取込フォームで既に「治療当日」「治療直後」ならそれを優先。
 */
export function enrichSnoreChartEvents<
  T extends { date: string; event: string },
>(
  points: T[],
  treatments: Array<{ scheduled_at?: string | null; status?: string | null }>,
  postDays = 2,
): T[] {
  const day0 = new Set<string>();
  const post = new Set<string>();
  for (const t of treatments) {
    if (t.status !== "done") continue;
    const ymd = treatmentYmdJst(t.scheduled_at);
    if (!ymd) continue;
    day0.add(ymd);
    for (let i = 1; i <= postDays; i++) post.add(addDaysYmd(ymd, i));
  }
  return points.map((p) => {
    if (p.event === "治療当日" || p.event === "治療直後") return p;
    if (day0.has(p.date)) return { ...p, event: "治療当日" };
    if (post.has(p.date)) return { ...p, event: "治療直後" };
    return p;
  });
}

/** 日付ごとの Health 指標（source 優先: oramemo > watch > health_unknown） */
export function preferVitalByDay(
  vitals: VitalLite[],
): Map<string, Map<string, number>> {
  const rank = (s: string) =>
    s === "oramemo" ? 0 : s === "watch" ? 1 : 2;
  const best = new Map<string, Map<string, { value: number; rank: number }>>();
  for (const v of vitals) {
    const dayMap = best.get(v.recorded_at) || new Map();
    const prev = dayMap.get(v.metric);
    const r = rank(v.source || "health_unknown");
    if (!prev || r < prev.rank) {
      dayMap.set(v.metric, { value: v.value, rank: r });
    }
    best.set(v.recorded_at, dayMap);
  }
  const out = new Map<string, Map<string, number>>();
  for (const [day, m] of best) {
    const nums = new Map<string, number>();
    for (const [metric, row] of m) nums.set(metric, row.value);
    out.set(day, nums);
  }
  return out;
}

export function formatHealthBitsForDay(
  byMetric: Map<string, number> | undefined,
): string {
  if (!byMetric || !byMetric.size) return "";
  const parts: string[] = [];
  const sleep = byMetric.get("sleep_hours");
  const spo2 = byMetric.get("spo2");
  const rr = byMetric.get("respiratory_rate");
  if (sleep != null) parts.push(`睡眠${sleep.toFixed(1)}h`);
  if (spo2 != null) parts.push(`SpO2 ${Math.round(spo2)}%`);
  if (rr != null) parts.push(`呼吸${rr.toFixed(1)}`);
  return parts.join(" / ");
}

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

/** 直近 N 日で Journal 欠落・いびき急変・Health食い違い等を拾い、未回答の問いを返す */
export function buildQuietEdgeAsks(input: {
  journals: JournalDailyRow[];
  notes: ContextNoteRow[];
  snore: SnoreLite[];
  vitals?: VitalLite[];
  treatments?: TreatmentLite[];
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
  const vitalsByDay = preferVitalByDay(
    (input.vitals || []).filter(
      (v) => v.recorded_at >= start && v.recorded_at <= today,
    ),
  );

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

  // 1c) いびきありなのに Health（睡眠/SpO2）欠測
  for (const s of snoreSorted) {
    if (s.recorded_at >= today) continue;
    const h = vitalsByDay.get(s.recorded_at);
    const hasSleep = h?.has("sleep_hours");
    const hasSpo2 = h?.has("spo2");
    if (hasSleep || hasSpo2) continue;
    const trigger = "health_gap";
    if (answered.has(`${s.recorded_at}|${trigger}`)) continue;
    asks.push({
      recorded_at: s.recorded_at,
      trigger,
      reason: "いびき記録あり・Health（睡眠/SpO2）なし",
      prompt: `${s.recorded_at} はいびき記録がありますが Health の睡眠・SpO2 がありません。測定漏れ／Shortcuts未実行／リング未同期など、思い当たることはありますか？`,
    });
  }

  // 1d) 治療実施日なのに Journal が空（メモも薄い）
  for (const t of input.treatments || []) {
    if (t.status !== "done") continue;
    const d = treatmentYmdJst(t.scheduled_at);
    if (!d || d < start || d >= today) continue;
    const j = journalByDay.get(d);
    const thin = !j || !j.excerpt.trim() || j.char_count < 40;
    if (!thin) continue;
    const trigger = "treatment_day_empty";
    if (answered.has(`${d}|${trigger}`)) continue;
    asks.push({
      recorded_at: d,
      trigger,
      reason: `${t.label || `第${t.session_no}回`}当日・メモ薄い`,
      prompt: `${d} はレーザー治療日（${t.label || `第${t.session_no}回`}）です。体調・痛み・睡眠の所感を短く残しますか？`,
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

  // 優先: spike → treatment → health_gap → lifestyle → missing journal
  const rank = (a: QuietEdgeAsk) => {
    switch (a.trigger) {
      case "snore_spike":
        return 0;
      case "treatment_day_empty":
        return 1;
      case "health_gap":
        return 2;
      case "journal_lifestyle":
        return 3;
      default:
        return 4;
    }
  };
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
